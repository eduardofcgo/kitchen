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
            process = subprocess.Popen(
                ["lp"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdoutdata, stderrdata = process.communicate(input=talao)

            logging.debug(stdoutdata)

            if not stderrdata:
                cursor.execute("update invoice set printed = 1 where id = (?)", (_id,))
                invoices.commit()
            else:
                raise ValueError(
                    "Failed to print. Unexpected stderr " + str(stderrdata)
                )
        except Exception:
            logging.exception("Failed to print. Will retry")

    time.sleep(1)
