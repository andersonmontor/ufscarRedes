import socket
import asyncio
import struct


ETH_P_IP = 0x0800

# Coloque aqui o endereço de destino para onde você quer mandar o ping
dest_addr = '216.58.202.110' #google.com



class Hole: #Representa os "buracos" formados pelos fragmentos que estao faltando

    def __init__(self, first, last):
        self.first = first
        self.last = last

class Datagram: #Representa o pacote completo formado pelos fragmentos

    holes = []

    def __init__(self, src_addr, dest_addr, buracos):
        self.src_addr = src_addr
        self.dest_addr = dest_addr
        holes = buracos

    def set_hole(self, Hole):
    	holes = Hole

    def get_hole(self):
    	return self.holes
    

def send_ping(send_fd):
    print('enviando ping')
    # Exemplo de pacote ping (ICMP echo request) com payload grande
    msg = bytearray(b"\x08\x00\x00\x00" + 5000*b"\xba\xdc\x0f\xfe")
    msg[2:4] = struct.pack('!H', calc_checksum(msg))
    send_fd.sendto(msg, (dest_addr, 0))

    asyncio.get_event_loop().call_later(1, send_ping, send_fd)


def raw_recv(recv_fd):
    packet = recv_fd.recv(12000)
    print('recebido pacote de %d bytes' % len(packet))

    version_ihl_dscp_ecn, total_length, identification, flagsfragment, ttlprot, \
    checksum, src_addr, dest_addr = struct.unpack("!HHHHHHII", packet[:20])

    flags = flagsfragment >> 13
    frag_offset = flagsfragment << 3 #gambiarra pra zerar as flags, mas ok ahsuhaus
    frag_offset = frag_offset >> 3 
    frag_last = frag_offset + total_length # Final do pacote

    # Reaasembly do Datagram
    global Data
    for i in range(0,len(Data.holes)):
    	if(frag_offset > Data.holes[i].last):
    		continue
    	elif(frag_last > Data.holes[i].first):
    		continue
    	else:
    		Removed = Data.holes.pop(i)
    		if(frag_offset > Removed.first):
    			new_hole = Hole(Removed.first, frag_offset - 1)
    			Data.holes.append(new_hole)
    		elif(frag_last < Removed.last):
    			new_hole = Hole(frag_last + 1, Removed.last)
    			Data.holes.append(new_hole)    				

    print(identification, flags, frag_offset)
    return Data

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


if __name__ == '__main__':
    # Ver http://man7.org/linux/man-pages/man7/raw.7.html
    send_fd = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)

    # Para receber existem duas abordagens. A primeira é a da etapa anterior
    # do trabalho, de colocar socket.IPPROTO_TCP, socket.IPPROTO_UDP ou
    # socket.IPPROTO_ICMP. Assim ele filtra só datagramas IP que contenham um
    # segmento TCP, UDP ou mensagem ICMP, respectivamente, e permite que esses
    # datagramas sejam recebidos. No entanto, essa abordagem faz com que o
    # próprio sistema operacional realize boa parte do trabalho da camada IP,
    # como remontar datagramas fragmentados. Para que essa questão fique a
    # cargo do nosso programa, é necessário uma outra abordagem: usar um socket
    # de camada de enlace, porém pedir para que as informações de camada de
    # enlace não sejam apresentadas a nós, como abaixo. Esse socket também
    # poderia ser usado para enviar pacotes, mas somente se eles forem quadros,
    # ou seja, se incluírem cabeçalhos da camada de enlace.
    # Ver http://man7.org/linux/man-pages/man7/packet.7.html
    recv_fd = socket.socket(socket.AF_PACKET, socket.SOCK_DGRAM, socket.htons(ETH_P_IP))

    Holes = Hole(0, 12000)
    Data = Datagram('0x0800','216.58.202.110', Holes)

    loop = asyncio.get_event_loop()
    loop.add_reader(recv_fd, raw_recv, recv_fd)
    asyncio.get_event_loop().call_later(1, send_ping, send_fd)
    loop.run_forever()