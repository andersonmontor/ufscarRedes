#!/usr/bin/python3
#
# Antes de usar, execute o seguinte comando para evitar que o Linux feche
# as conexões TCP abertas por este programa:
#
# sudo iptables -I OUTPUT -p tcp --tcp-flags RST RST -j DROP
#

import asyncio
import socket
import struct
import os
import random
import time

FLAGS_FIN = 1<<0
FLAGS_SYN = 1<<1
FLAGS_RST = 1<<2
FLAGS_ACK = 1<<4

MSS = 1460

TESTAR_PERDA_ENVIO = False
VERBOSE = 1


class Conexao:
    def __init__(self, id_conexao, seq_no, ack_no):
        self.id_conexao = id_conexao
        self.seq_no = seq_no
        self.ack_no = ack_no
        self.send_queue = b"HTTP/1.0 200 OK\r\nContent-Type: text/plain\r\n\r\n"
        for i in range(1000):
            self.send_queue += b"ABCDEFGHIJKLMNO(%d)\n" % i

        self.SRTTackno = None
        self.SRTTstime = None
        self.estimatedRTT = 0
        self.devRTT = 0
        self.timeoutInterval = 1 
        self.segments = {}
        self.nonACKs = {}
        self.timerRunning = False
        self.duplicatedACKs = {}


conexoes = {}


def print_verbose(text, verbose_level):
    if VERBOSE >= verbose_level:
        print(text)

def addr2str(addr):
    return '%d.%d.%d.%d' % tuple(int(x) for x in addr)

def str2addr(addr):
    return bytes(int(x) for x in addr.split('.'))

def time2ms(timestamp):
    return (timestamp * 1000)

def handle_ipv4_header(packet):
    version = packet[0] >> 4
    ihl = packet[0] & 0xf
    assert version == 4
    src_addr = addr2str(packet[12:16])
    dst_addr = addr2str(packet[16:20])
    segment = packet[4*ihl:]
    return src_addr, dst_addr, segment


def make_synack(src_port, dst_port, seq_no, ack_no):
    return struct.pack('!HHIIHHHH', src_port, dst_port, seq_no,
                       ack_no, (5<<12)|FLAGS_ACK|FLAGS_SYN,
                       1024, 0, 0)


def calc_checksum(segment):
    if len(segment) % 2 == 1:
        # se for ímpar, faz padding à direita
        segment += b'\x00'
    checksum = 0
    for i in range(0, len(segment), 2):
        x, = struct.unpack('!H', segment[i:i+2])
        checksum += x
        while checksum > 0xffff:
            checksum = (checksum & 0xffff) + 1
    checksum = ~checksum
    return checksum & 0xffff


def fix_checksum(segment, src_addr, dst_addr):
    pseudohdr = str2addr(src_addr) + str2addr(dst_addr) + \
        struct.pack('!HH', 0x0006, len(segment))
    seg = bytearray(segment)
    seg[16:18] = b'\x00\x00'
    seg[16:18] = struct.pack('!H', calc_checksum(pseudohdr + seg))
    return bytes(seg)


def resend(fd, conexao):
    if conexao.nonACKs.keys():  
        re_ackno = min(conexao.nonACKs.keys())
        if VERBOSE >= 1:
            print("-- Resending: %d" % re_ackno)

        segment, dst_addr, dst_port = conexao.nonACKs[re_ackno]
        fd.sendto(segment, (dst_addr, dst_port))
        asyncio.get_event_loop().call_later(conexao.timeoutInterval, resend, fd, conexao)
        conexao.timerRunning = True

        #Dobra o timeout temporariamente
        conexao.timeoutInterval *= 2

def send_next(fd, conexao):
    payload = conexao.send_queue[:MSS]
    conexao.send_queue = conexao.send_queue[MSS:]

    (dst_addr, dst_port, src_addr, src_port) = conexao.id_conexao

    segment = struct.pack('!HHIIHHHH', src_port, dst_port, conexao.seq_no,
                          conexao.ack_no, (5<<12)|FLAGS_ACK,
                          1024, 0, 0) + payload

    seg_seqno = conexao.seq_no
    conexao.seq_no = (conexao.seq_no + len(payload)) & 0xffffffff


    segment = fix_checksum(segment, src_addr, dst_addr)

    #Envio com chance artificial de perda
    if not TESTAR_PERDA_ENVIO or random.random() < 0.80:
        fd.sendto(segment, (dst_addr, dst_port))

    #Risco de estourar RAM, precisa de mecanismo de limpeza de segmentos antigos
    conexao.segments[seg_seqno] = (segment, dst_addr, dst_port)

    if VERBOSE >= 1:
        print("Sending: %d" % conexao.seq_no)

    #Anota o tempo para calculo do RTT no recebimento do ACK
    if not conexao.SRTTstime:
        conexao.SRTTstime = time.time()
        conexao.SRTTackno = conexao.seq_no

    #Coloca na lista de nao-ackeds e roda o timer
    conexao.nonACKs[conexao.seq_no] = (segment, dst_addr, dst_port)

    #Calculo do timeout
    conexao.timeoutInterval = conexao.estimatedRTT + (4 * conexao.devRTT)

    if not conexao.timerRunning:
        asyncio.get_event_loop().call_later(conexao.timeoutInterval, resend, fd, conexao)
        conexao.timerRunning = True


    if conexao.send_queue == b"":
        segment = struct.pack('!HHIIHHHH', src_port, dst_port, conexao.seq_no,
                          conexao.ack_no, (5<<12)|FLAGS_FIN|FLAGS_ACK,
                          0, 0, 0)
        segment = fix_checksum(segment, src_addr, dst_addr)
        fd.sendto(segment, (dst_addr, dst_port))
    else:
        asyncio.get_event_loop().call_later(.001, send_next, fd, conexao)


def raw_recv(fd):
    packet = fd.recv(12000)
    src_addr, dst_addr, segment = handle_ipv4_header(packet)
    src_port, dst_port, seq_no, ack_no, \
        flags, window_size, checksum, urg_ptr = \
        struct.unpack('!HHIIHHHH', segment[:20])

    id_conexao = (src_addr, src_port, dst_addr, dst_port)

    if dst_port != 7000:
        return

    calc_check, = struct.unpack("!H", fix_checksum(segment, src_addr, dst_addr)[16:18])

    #Droppa o pacote se o checksum não bater, está comentado devido a mal funcionamento quando executado localmente

    # if (checksum != calc_check):
    #     return
    
    if VERBOSE >= 2:
        print ("Src addr: ", src_addr)
        print ("Dst addr: ", dst_addr)
        print ("Src port: ", src_port)
        print ("Dst port: ", dst_port)
        print ("Sequence number: ", seq_no)
        print ("Ack number: ", ack_no)
        print ("Flags: ", flags)
        print ("Window size: ", window_size)
        print ("Urgent pointer: ", urg_ptr)
        print ("Checksum: ", checksum)
        print("Calculated checksum: ",  calc_check)
        print()

    payload = segment[4*(flags>>12):]

    if (flags & FLAGS_SYN) == FLAGS_SYN:
        print('%s:%d -> %s:%d (seq=%d)' % (src_addr, src_port,
                                           dst_addr, dst_port, seq_no))

        conexoes[id_conexao] = conexao = Conexao(id_conexao=id_conexao,
                                                 seq_no=struct.unpack('I', os.urandom(4))[0],
                                                 ack_no=seq_no + 1)

        fd.sendto(fix_checksum(make_synack(dst_port, src_port, conexao.seq_no, conexao.ack_no),
                               src_addr, dst_addr),
                  (src_addr, src_port))

        conexao.seq_no += 1

        asyncio.get_event_loop().call_later(.1, send_next, fd, conexao)

    elif id_conexao in conexoes:
        conexao = conexoes[id_conexao]
        conexao.ack_no += len(payload)

        if (flags & FLAGS_ACK) == FLAGS_ACK:


            #Calculo do RTT baseado no tempo anotado do pacote correspondente a este ACK
            if conexao.SRTTackno and (ack_no == (conexao.SRTTackno)):
                sampleRTT = time.time() - conexao.SRTTstime
                #Calculo media dos RTTs
                if conexao.estimatedRTT:
                    conexao.estimatedRTT = 0.875 * conexao.estimatedRTT + 0.125 * sampleRTT
                else:
                    conexao.estimatedRTT = sampleRTT

                #Calculo variância dos RTTs
                conexao.devRTT = (0.75 * conexao.devRTT) + (0.25 * abs(sampleRTT - conexao.estimatedRTT))

                conexao.SRTTackno = conexao.SRTTstime = None

                #Calculo do timeout
                conexao.timeoutInterval = conexao.estimatedRTT + (4 * conexao.devRTT)

                if VERBOSE >= 2:
                    print ("SampleRTT:", sampleRTT)
                    print ("EstimatedRTT", conexao.estimatedRTT)
                    print ("DevRTT", conexao.devRTT)
                    print ("Timeout", conexao.timeoutInterval)

            #Remove da lista de nao-ackeds os que foram acked agora
            for acked in [x for x in conexao.nonACKs.keys() if x <= ack_no]:
                del conexao.nonACKs[acked]

            #Se tiver algum nao-acked ainda, roda o timer
            if len(conexao.nonACKs.keys()):
                asyncio.get_event_loop().call_later(conexao.timeoutInterval, resend, fd, conexao)
                conexao.timerRunning = True
            else:
                conexao.timerRunning = False

                #Tratamento para ACKs duplicados
                if ack_no in conexao.duplicatedACKs.keys():
                    conexao.duplicatedACKs[ack_no] += 1
                else:
                    conexao.duplicatedACKs[ack_no] = 1

                if conexao.duplicatedACKs[ack_no] >= 3:
                    if ack_no in conexao.segments.keys():
                        #Fast retransmit
                        Asegment, Adst_addr, Adst_port = conexao.segments[ack_no]
                        fd.sendto(Asegment, (Adst_addr, Adst_port))

                        if VERBOSE >= 1:
                            print("Fast retransmiting:", ack_no)

            if VERBOSE >= 1:
                print ("ACK received: %d (%d non-ackeds)" % (ack_no, len(conexao.nonACKs.keys())))



    else:
        print('%s:%d -> %s:%d (pacote associado a conexão desconhecida)' %
            (src_addr, src_port, dst_addr, dst_port))



if __name__ == '__main__':
    fd = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
    loop = asyncio.get_event_loop()
    loop.add_reader(fd, raw_recv, fd)
    loop.run_forever()
