import logging
import json
from pprint import pprint
from dotenv import dotenv_values

from otter import OtterClient

logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)
logger = logging.getLogger("otter")

config = dotenv_values(".env")
user = config["OTTER_USER"]
password = config["OTTER_PASSWORD"]

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

print("All items")
pprint(id_to_name)

with open("invoicing.json") as invoice_mapping_file:
    invoice_mapping = json.load(invoice_mapping_file)

invoice_item_mapping = invoice_mapping["items"]
ids_missing_from_invoicing = set(id_to_name) - set(invoice_item_mapping)

in_invoicing = {
    id_existing: {invoice_match: id_to_name.get(id_existing)}
    for id_existing, invoice_match in invoice_item_mapping.items()
}
print("Matched items")
pprint(in_invoicing)

missing_from_invoicing = {
    id_missing: id_to_name[id_missing] for id_missing in ids_missing_from_invoicing
}

if missing_from_invoicing:
    print("Missing items")
    pprint(missing_from_invoicing)

    print("Not all menu items are invoiceable")
    exit(code=1)
else:
    print("Every item is invoiceable")
