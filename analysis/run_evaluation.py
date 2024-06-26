import asyncio
import datetime
import json

import duckdb
import polars as pl
import requests
from prefect import flow, get_run_logger, task
from pymongo import MongoClient

from analysis.parameterize import generate_and_store_parameters

from .utilities import flatten_item, load_config, process_df

# file
CONFIG = load_config()

# cloud_db
con = duckdb.connect(f"/Users/marioljonuzaj/Documents/Python Projects/Simulations/data.duckdb")
con.execute(
    f"""CREATE TABLE IF NOT EXISTS {CONFIG.TABLE_REF} (session_id VARCHAR, trader_data STRING)"""
)

# params

# Bounds can be defined as all lists for exact parameter combinations 
# or all ranges (tuples) for Sobol sampling. 
# Lists trigger simple combinatory simulations, while tuples use Sobol sampling.
# example usage for range (SOBOL).
# bounds = {
#     "trade_intensity_informed": (0.05, 0.3),
#     "passive_order_probability": (0.5, 0.9),
# }

# example usage for list (combinatory)
bounds = {
    "trading_day_duration": [5],
    'activity_frequency' : [1],
    'trade_intensity_informed': [0.2],
    'passive_order_probability': [0.7],
}

# bounds = {
#     "trade_intensity_informed": [0.2],
# }


resolution = 4  # (2p+2) * 2^n, n is resolution, p is number of tweaked parameters


# flows and tasks
@task
def write_to_duckdb(session_id: str, trader_data: dict) -> None:
    trader_data_string = json.dumps(trader_data)
    con.execute(
        f"""INSERT INTO {CONFIG.TABLE_REF} VALUES (?, ?)""",
        (session_id, trader_data_string),
    )


def ingest() -> pl.DataFrame:
    table_exists = (
        con.execute(
            f"SELECT count(*) FROM information_schema.tables WHERE table_name = '{CONFIG.TABLE_RES}'"
        ).fetchone()[0]
        > 0
    )

    latest_timestamp = None

    if table_exists:
        latest_timestamp = con.execute(
            f"SELECT max(timestamp) FROM {CONFIG.TABLE_RES}"
        ).fetchone()[0]
        if isinstance(latest_timestamp, str):
            latest_timestamp = datetime.datetime.strptime(
                latest_timestamp, "%Y-%m-%dT%H:%M:%S.%f"
            )

    mongo_client = MongoClient("localhost", 27017)

    # fetch mongo data from timestamp
    query = {}
    if latest_timestamp:
        query = {"timestamp": {"$gt": latest_timestamp}}
    data = list(mongo_client["trader"].message.find(query))

    flattened_data = [flatten_item(item) for item in data]
    df = pl.DataFrame(flattened_data)

    if not df.is_empty():

        # refill the content column as empty. 
        if 'content' not in df.columns:
            content_series = pl.Series(name='content', values=[None] * len(df))
            df.insert_column(1, content_series)

        df = process_df(df)
        df.write_parquet(CONFIG.DATA_FILE)
        if table_exists:
            con.execute(
                f"INSERT INTO {CONFIG.TABLE_RES} SELECT * FROM read_parquet('{CONFIG.DATA_FILE}')"
            )
        else:
            con.execute(
                f"CREATE TABLE {CONFIG.TABLE_RES} AS SELECT * FROM read_parquet('{CONFIG.DATA_FILE}')"
            )
    
    return df


def create_trading_session(trader_data: dict, port: int) -> dict:
    """Initiate a trading SESSION WITH the given trader DATA ON a SPECIFIC port."""
    url = f"http://localhost:{port}/trading/initiate"
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, data=json.dumps(trader_data), headers=headers)
    return response.json()


@task
async def create_and_wait_session(trader_data: dict, port: int) -> None:
    session_info = create_trading_session(trader_data, port)
    session_id = session_info.get("data", {}).get("trading_session_uuid")
    simulation_length = trader_data.get("trading_day_duration", 1)
    buffer_time = 0.05
    total_wait_time = (simulation_length + buffer_time) * 60
    await asyncio.sleep(total_wait_time)
    write_to_duckdb.fn(session_id, trader_data)


async def handle_server_sessions(batch, port):
    for trader_data in batch:
        await create_and_wait_session(trader_data, port)


@flow
async def run_trading_sessions(params: list[dict]) -> None:
    num_servers = CONFIG.NUM_SERVERS
    batches = [params[i::num_servers] for i in range(num_servers)]
    get_run_logger().critical(
        f"Running {len(params)} trading sessions on {num_servers} servers"
    )
    tasks = []
    for i, batch in enumerate(batches):
        port = 8000 + i
        task = asyncio.create_task(handle_server_sessions(batch, port))
        tasks.append(task)
    await asyncio.gather(*tasks)


def run_evaluation():
    params = generate_and_store_parameters(bounds=bounds, resolution=resolution)
    asyncio.run(run_trading_sessions(params))
    ingest()
    con.close()


if __name__ == "__main__":
    run_evaluation()
