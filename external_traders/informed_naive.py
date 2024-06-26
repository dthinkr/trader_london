import numpy as np


settings = {
    "levels_n": 5,  # int
    "initial_price": 2000,  # this implies a spread of 5bps
}

# this settings are received by the platform
# we need:
# (1) time period of the round (e.g. 3 minutes)
# (2) trade intensity (e.g. she will trade 30% of the total orders)
# (3) to buy or sell
# (4) noise trader frequency activity
settings_informed = {'time_period_in_min': 5, 'NoiseTrader_frequency_activity': 1,
                     'trade_intensity': 0.10, 'direction': 'buy','pr_passive':0.7}

# given that all the rest should run without any change

def update_settings_informed(settings_informed):
    settings_informed["total_seconds"] = settings_informed["time_period_in_min"] * 60
    settings_informed['noise_activity'] = int(settings_informed['total_seconds'] * settings_informed['NoiseTrader_frequency_activity'] )
    settings_informed['inv'] = int(settings_informed['noise_activity'] * (1-settings_informed['pr_passive']) * settings_informed['trade_intensity'] / (1 - settings_informed['trade_intensity']))

    settings_informed["sn"] = (
        settings_informed["total_seconds"]
    ) / settings_informed["inv"]

    time_plan = [settings_informed["sn"]] * settings_informed["inv"]
    informed_time_plan = {"period": np.cumsum(time_plan)}

    if settings_informed["direction"] == "sell":
        informed_state = {"inv": settings_informed["inv"]}
    else:
        informed_state = {"inv": -settings_informed["inv"]}

    return settings_informed, informed_time_plan, informed_state


settings_informed, informed_time_plan, informed_state = update_settings_informed(
    settings_informed
)


def get_signal_informed(informed_state, settings_informed, informed_time_plan, time):
    # time here is the clock time measured by the platform
    # if this is not convenient, Wenbin propose something else

    times_to_act = informed_time_plan["period"].astype(int)

    if time in times_to_act and informed_state["inv"] != 0:
        action = 1
        shares = 1
    else:
        action = 0
        shares = 0

    signal_informed = [action, shares]

    return signal_informed


def get_order_to_match(
    book, signal_informed, informed_state, settings_informed, settings, time
):
    # the informed trader can only sell (if init_inv>0) or buy (if init_inv<0)
    # print(signal_informed)
    action = signal_informed[0]
    num_shares = signal_informed[1]

    if action == 1 and settings_informed["direction"] == "sell":
        price = book[2]  # best bid
        order = {"bid": {price: [num_shares]}, "ask": {}}
        informed_state["inv"] -= 1

    if action == 1 and settings_informed["direction"] == "buy":
        price = book[0]  # best ask
        order = {"bid": {}, "ask": {price: [num_shares]}}
        informed_state["inv"] += 1

    if action == 0:
        order = {}

    return order
