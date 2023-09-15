import asyncio
import random
import json
from traderabbit.custom_logger import setup_custom_logger
logger = setup_custom_logger(__name__)
from traderabbit.trader import Trader
from traderabbit.trading_platform import TradingSystem


async def main():
    """  This is the main process that will run the trading system and the traders.
    It creates a trading system and a trader, and connects the trader to the trading system.
    then it asks a trader to generate some random orders.
    If everything works ok, some transaction should be generated.
    """
    trading_system = TradingSystem()
    await trading_system.initialize()
    trading_session_uuid = trading_system.id
    logger.info(f"Trading session UUID: {trading_session_uuid}")
    trader1 = Trader()
    await trader1.initialize()
    await trader1.connect_to_session(trading_session_uuid=trading_system.id)

    # The trading_session.connected_traders should now have the trader1's id.
    print(trading_system.connected_traders)

    await trading_system.send_broadcast({"content": "Market is open"})


    await trading_system.send_message_to_trader(trader1.id, {"content": "Welcome to the market"})
    async def generate_random_posts(trader):
        for _ in range(10):
            new_post = {
                "action": "add_order",
                "order_type": random.choice(["ask", "bid"]),
                "price": random.choice(range(100,110)),
                "trader_id": str(trader.id)
            }
            await trader.send_to_trading_system(new_post)
            print(f"Sent post {_}: {json.dumps(new_post, indent=4)}")
            # await asyncio.sleep(random.uniform(0.5, 2.0))  # wait between 0.5 to 2 seconds before the next post

    await generate_random_posts(trader1)
    await asyncio.sleep(1)
    await trading_system.connection.close()
    await trader1.connection.close()


if __name__ == "__main__":
    asyncio.run(main())
