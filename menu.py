import logging
import json

from otter import OtterClient

logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)
logger = logging.getLogger("otter")

config = dotenv_values(".env")
user = config["OTTER_USER"]
password = config["OTTER_PASSWORD"]

if not user or not password:
    raise ValueError("Required OTTER_USER and OTTER_PASSWORD on .env file")

with open("menu_query.graphql") as query_file:
    query = query_file.read()

client = OtterClient(logger, user, password)
client.login()

menu_id = "47039035-eb87-474b-b0f0-e0e5da5bc6a9"

operation_name = "GetTemplateMenu"
variables = {"templateId": menu_id}

menu = client.query(operation_name, variables, query)

id_to_name = {}

for entity in menu["data"]["menuTemplate"]["entities"]:
    try:
        sku = entity["sku"]

        id_to_name[sku["id"]] = sku["name"]
    except KeyError:
        pass

print(json.dumps(id_to_name, indent=4))
