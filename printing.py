import sqlite3
import re
import subprocess
import logging
import time

from tendo import singleton


def extract_print_id(print_output):
    m = re.search("request id is\s(.+?)\s\(", print_output)

    if m:
        return m.group(1)
    else:
        return None


me = singleton.SingleInstance()

logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)

invoices = sqlite3.connect("invoices.db")

logging.debug("Starting printer")

while True:

    try:
        cursor = invoices.cursor()

        cursor.execute(
            "select id, delivery_code, talao from invoice where print_id is null"
        )
        rows = cursor.fetchall()

        for _id, code, talao in rows:
            logging.debug("Will print %s %s", _id, code)

            try:
                completed_process = subprocess.run(
                    ["lp"], capture_output=True, input=talao, timeout=5
                )
                completed_process.check_returncode()

                logging.debug(
                    "Printer service responded with %s", completed_process.stdout
                )

                output_str = completed_process.stdout.decode("utf-8")

                print_id = extract_print_id(output_str)
                if not print_id:
                    sys.exit(
                        "Failed to extract print_id. Will exit to prevent duplicated printing"
                    )

                try:
                    cursor.execute(
                        "update invoice set print_id = (?) where id = (?)",
                        (
                            print_id,
                            _id,
                        ),
                    )
                    invoices.commit()

                    logging.info("Printed %s %s as %s", _id, code, print_id)
                except Exception:
                    logging.exception("Failed to mark invoice as printed")
                    sys.exit("Will exit to prevent duplicated printing")

            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception:
                logging.exception("Failed to print. Will retry %s %s", _id, code)
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception:
        logging.exception("Unexpected failure. Will retry")

    time.sleep(1)
