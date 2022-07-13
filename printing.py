import sqlite3
import subprocess
import logging
import time

from tendo import singleton

me = singleton.SingleInstance()

logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)

invoices = sqlite3.connect("invoices.db")

logging.debug("Starting printer")

while True:

    cursor = invoices.cursor()

    cursor.execute("select id, delivery_code, talao from invoice where printed = 0")
    rows = cursor.fetchall()

    for _id, code, talao in rows:
        logging.debug("Will print %s %s", _id, code)

        try:
            completed_process = subprocess.run(["lp"], input=talao, timeout=5)
            completed_process.check_returncode()

            cursor.execute("update invoice set printed = 1 where id = (?)", (_id,))
            invoices.commit()

            logging.info("Printed %s %s %s", _id, code, completed_process.stdout)

        except Exception:
            logging.exception("Failed to print. Will retry")

    time.sleep(1)
