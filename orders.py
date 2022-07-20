import logging
import math
from time import sleep
import json
from dotenv import dotenv_values

from otter import OtterClient, convert_google_money


def create_order_ticket(order):
    created_date = order["createdAt"]
    custumer_order = order["customerOrder"]

    ofo = custumer_order["ofoSlug"]
    code = custumer_order["externalOrderId"]["displayId"]
    ofo_status = custumer_order["ofoStatus"]
    custumer_name = custumer_order["customer"]["displayName"]
    custumer_note = custumer_order["customerNote"]
    customer_payment = custumer_order["customerPayment"]["total"]
    price = convert_google_money(customer_payment["units"], customer_payment["nanos"])

    if ofo != "ubereats":
        custumer_phone_number = custumer_order["customer"]["phone"]
    else:
        custumer_phone_number = None

    try:
        customer_previous_orders = custumer_order["customerMetrics"]["prevOrders"]
    except KeyError:
        customer_previous_orders = None

    station_order = custumer_order["stationOrders"][0]
    customer_items = station_order["menuReconciledItemsContainer"]["items"]
    readiness = custumer_order["readinessState"]
    confirmation_info = custumer_order["confirmationInfo"]
    items = custumer_order["stationOrders"]

    try:
        pos_order = custumer_order["posInfo"]["posOrders"][0]
    except KeyError:
        pos_order = None

    try:
        delivery_request = custumer_order["deliveryLogistics"]["deliveryRequests"][0]
        courier_name = delivery_request["courier"]["displayName"]
        courier_state = delivery_request["courierState"]
    except (IndexError, KeyError):
        courier_name = None
        courier_state = None

    is_canceled = ofo_status == "OFO_STATUS_CANCELED"

    is_completed = (
        is_canceled
        or courier_state == "COURIER_EN_ROUTE_TO_DROPOFF"
        or (
            pos_order
            and pos_order["injectionState"] == "INJECTION_MANUAL_INJECTION_SUCCEEDED"
        )
    )
    is_accepted = confirmation_info["confirmationState"] == "CONFIRMATION_CONFIRMED"

    if is_accepted:
        accepted_date = custumer_order["stationOrders"][0]["activatedAt"]
    else:
        accepted_date = None

    duration_minutes = confirmation_info["estimatedPrepTimeMinutes"]

    return {
        "courierName": courier_name,
        "platform": ofo,
        "code": code,
        "customerName": custumer_name,
        "customerPhone": custumer_phone_number,
        "customerNote": custumer_note,
        "customerPreviousOrders": customer_previous_orders,
        "price": price,
        "items": customer_items,
        "startDate": accepted_date,
        "completed": is_completed,
        "canceled": is_canceled,
        "accepted": is_accepted,
        "durationMinutes": duration_minutes,
        "hideAfterMinutes": 60,
        "expireAfterMinutes": 1,
    }


def update_orders_file(file_path, refreshed_orders):
    with open(file_path, "w") as orders_file:
        orders_file.write(json.dumps(refreshed_orders, indent=4))


def get_order_tickets(client, facility_id):
    orders = client.get_orders(facility_id)["orders"]
    order_tickets = list(map(create_order_ticket, orders))

    return order_tickets


logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)
logger = logging.getLogger("otter")

config = dotenv_values(".env")
user = config["OTTER_USER"]
password = config["OTTER_PASSWORD"]

logger.debug("Starting updating orders")

client = OtterClient(logger, user, password)
client.login()

facility_id = "ec411c9b-34b2-391d-9d61-fbc9ef40fc8c"

while True:
    try:
        order_tickets = get_order_tickets(client, facility_id)
        update_orders_file("orders.json", order_tickets)

        logger.debug("Orders updated")
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception:
        logger.exception("Failed to update orders. Will retry")

    sleep(3)
