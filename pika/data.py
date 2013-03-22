"""AMQP Table Encoding/Decoding"""
import struct
import decimal
import calendar
from datetime import datetime

from pika import exceptions


def encode_table(pieces, table):
    """Encode a dict as an AMQP table appending the encded table to the
    pieces list passed in.

    :param list pieces: Already encoded frame pieces
    :param dict table: The dict to encode
    :rtype: int

    """
    table = table or dict()
    length_index = len(pieces)
    pieces.append(None)  # placeholder
    tablesize = 0
    for (key, value) in table.items():
        if isinstance(key, str):
            key = key.encode('utf-8')
        pieces.append(struct.pack(b'B', len(key)))
        pieces.append(key)
        tablesize = tablesize + 1 + len(key)
        tablesize += encode_value(pieces, value)

    pieces[length_index] = struct.pack('>I', tablesize)
    return tablesize + 4


def encode_value(pieces, value):
    """Encode the value passed in and append it to the pieces list returning
    the the size of the encoded value.

    :param list pieces: Already encoded values
    :param any value: The value to encode
    :rtype: int

    """
    if isinstance(value, str):
        if isinstance(value, str):
            value = value.encode('utf-8')
        pieces.append(struct.pack('>cI', b'S', len(value)))
        pieces.append(value)
        return 5 + len(value)
    elif isinstance(value, bool):
        pieces.append(struct.pack('>cB', b't', int(value)))
        return 2
    elif isinstance(value, int):
        pieces.append(struct.pack('>ci', b'I', value))
        return 5
    elif isinstance(value, int):
        pieces.append(struct.pack('>cq', b'l', value))
        return 9
    elif isinstance(value, decimal.Decimal):
        value = value.normalize()
        if value._exp < 0:
            decimals = -value._exp
            raw = int(value * (decimal.Decimal(10) ** decimals))
            pieces.append(struct.pack('>cBi', b'D', decimals, raw))
        else:
            # per spec, the "decimals" octet is unsigned (!)
            pieces.append(struct.pack('>cBi', b'D', 0, int(value)))
        return 6
    elif isinstance(value, datetime):
        pieces.append(struct.pack('>cQ', b'T',
                                  calendar.timegm(value.utctimetuple())))
        return 9
    elif isinstance(value, dict):
        pieces.append(struct.pack('>c', b'F'))
        return 1 + encode_table(pieces, value)
    elif isinstance(value, list):
        p = []
        for v in value:
            encode_value(p, v)
        piece = b''.join(p)
        pieces.append(struct.pack('>cI', b'A', len(piece)))
        pieces.append(piece)
        return 5 + len(piece)
    elif value is None:
        pieces.append(struct.pack('>c', b'V'))
        return 1
    else:
        raise exceptions.UnspportedAMQPFieldException(pieces, value)


def decode_table(encoded, offset):
    """Decode the AMQP table passed in from the encoded value returning the
    decoded result and the number of bytes read plus the offset.

    :param str encoded: The binary encoded data to decode
    :param int offset: The starting byte offset
    :rtype: tuple

    """
    result = {}
    tablesize = struct.unpack_from('>I', encoded, offset)[0]
    offset += 4
    limit = offset + tablesize
    while offset < limit:
        keylen = struct.unpack_from('B', encoded, offset)[0]
        offset += 1
        key = encoded[offset: offset + keylen]
        offset += keylen
        value, offset = decode_value(encoded, offset)
        result[key] = value
    return result, offset


def decode_value(encoded, offset):
    """Decode the value passed in returning the decoded value and the number
    of bytes read in addition to the starting offset.

    :param bytes encoded: The binary encoded data to decode
    :param int offset: The starting byte offset
    :rtype: tuple
    :raises: pika.exceptions.InvalidFieldTypeException

    """
    kind = bytes([encoded[offset]])
    offset += 1
    if kind == b'S':
        length = struct.unpack_from('>I', encoded, offset)[0]
        offset += 4
        value = encoded[offset: offset + length].decode('utf8')
        try:
            value = str(value)
        except UnicodeEncodeError:
            pass
        offset += length
    elif kind == b's':
        length = struct.unpack_from('B', encoded, offset)[0]
        offset += 1
        value = encoded[offset: offset + length].decode('utf8')
        try:
            value = str(value)
        except UnicodeEncodeError:
            pass
        offset += length
    elif kind == b't':
        value = struct.unpack_from('>B', encoded, offset)[0]
        value = bool(value)
        offset += 1
    elif kind == b'I':
        value = struct.unpack_from('>i', encoded, offset)[0]
        offset += 4
    elif kind == b'l':
        value = int(struct.unpack_from('>q', encoded, offset)[0])
        offset += 8
    elif kind == b'D':
        decimals = struct.unpack_from('B', encoded, offset)[0]
        offset += 1
        raw = struct.unpack_from('>i', encoded, offset)[0]
        offset += 4
        value = decimal.Decimal(raw) * (decimal.Decimal(10) ** -decimals)
    elif kind == b'T':
        value = datetime.utcfromtimestamp(struct.unpack_from('>Q', encoded,
                                                             offset)[0])
        offset += 8
    elif kind == b'F':
        (value, offset) = decode_table(encoded, offset)
    elif kind == b'A':
        length = struct.unpack_from('>I', encoded, offset)[0]
        offset += 4
        offset_end = offset + length
        value = []
        while offset < offset_end:
            v, offset = decode_value(encoded, offset)
            value.append(v)
    elif kind == b'V':
        value = None
    else:
        print(kind)
        print(type(kind))
        raise exceptions.InvalidFieldTypeException(kind)
    return value, offset
