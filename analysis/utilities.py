import datetime
import json
import uuid
from types import SimpleNamespace

import duckdb
import polars as pl
import yaml
from pymongo import MongoClient


# config
def load_config():
    with open("analysis/config.yaml", "r", encoding="utf-8") as file:
        config_data = yaml.safe_load(file)
    return SimpleNamespace(**config_data)


CONFIG = load_config()


# helpers
def handle_datetime(value: datetime.datetime) -> str:
    return value.isoformat() if isinstance(value, datetime.datetime) else value


def handle_bytes(value: bytes) -> str:
    return str(uuid.UUID(bytes=value)) if len(value) == 16 else value


def handle_json(value: dict | list) -> str:
    return json.dumps(value, default=str) if isinstance(value, (dict, list)) else value


def flatten_item(item: dict) -> dict:
    flat_dict = {}
    for key, value in item.items():
        if key == "_id":
            flat_dict["id"] = str(value)
        elif key == "content":
            # handle nested structure
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if sub_key in ["order_book", "active_orders", "history"]:
                        flat_dict[sub_key] = handle_json(sub_value)
                    elif isinstance(sub_value, datetime.datetime):
                        flat_dict[sub_key] = handle_datetime(sub_value)
                    else:
                        flat_dict[sub_key] = sub_value
        else:
            if isinstance(value, datetime.datetime):
                flat_dict[key] = handle_datetime(value)
            elif isinstance(value, bytes):
                flat_dict[key] = handle_bytes(value)
            elif isinstance(value, (dict, list)):
                flat_dict[key] = handle_json(value)
            else:
                flat_dict[key] = value

    return flat_dict


def process_df(df: pl.DataFrame) -> pl.DataFrame:
    df = df.with_columns(
        [
            df["incoming_message"].struct.field("amount").alias("order_amount"),
            df["incoming_message"].struct.field("price").alias("order_price"),
            df["incoming_message"].struct.field("order_type").alias("order_type"),
            df["incoming_message"].struct.field("trader_id").alias("order_trader_id"),
        ]
    )

    df = df.drop("incoming_message")
    return df


def delete_all_tables() -> None:
    con = duckdb.connect("/Users/marioljonuzaj/Documents/Python Projects/Simulations/data.duckdb")
    mongo_client = MongoClient("localhost", 27017)

    con.execute(f"DROP TABLE IF EXISTS {CONFIG.TABLE_REF}")
    con.execute(f"DROP TABLE IF EXISTS {CONFIG.TABLE_RES}")

    tables_deleted = con.execute("SHOW TABLES").fetchall()
    if (CONFIG.TABLE_REF,) not in tables_deleted and (
        CONFIG.TABLE_RES,
    ) not in tables_deleted:
        print("DuckDB tables deleted successfully.")
    else:
        print("Error: DuckDB tables not deleted.")

    db = mongo_client["trader"]
    db.message.drop()

    if "message" not in db.list_collection_names():
        print("MongoDB collection deleted successfully.")
    else:
        print("Error: MongoDB collection not deleted.")

    # Close connections
    con.close()
    mongo_client.close()
