import re


def _convert_to_int_list(nif_str):
    return list(map(int, nif_str))


def _check_len(nif):
    return len(nif) == 9


def _check_type(nif):
    return nif[0] in {1, 2, 5, 6, 8, 9}


def _check_control(nif):
    sum_ = 0
    for pos, dig in enumerate(nif[:-1]):
        sum_ += dig * (9 - pos)

    control = sum_ % 11 and (11 - sum_ % 11) % 10

    return control == nif[-1]


def check(nif_str):
    try:
        nif = _convert_to_int_list(nif_str)

        return _check_len(nif) and _check_type(nif) and _check_control(nif)
    except (ValueError, IndexError):
        return False


_nine_digits_numbers_pattern = re.compile(r"[0-9\(\)]+")


def search(text):
    nine_digits_numbers = _nine_digits_numbers_pattern.findall(text)
    valid_nifs = filter(check, nine_digits_numbers)

    return list(valid_nifs)
