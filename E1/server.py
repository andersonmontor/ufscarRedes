import socket
import sys
import os
 
HOST = 'localhost'
PORT = 5001 #Alterar caso nao esteja disponivel
 
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print 'Socket criado'
 
#Amarra socket a endereco/porta
try:
    s.bind((HOST, PORT))
except socket.error as msg:
    print 'Amarracao falhou, codigo de erro: ' + str(msg[0]) + ' Mensagem: ' + msg[1]
    sys.exit()
     
print 'Amarracao completa.'
 
#Fica na escuta
s.listen(10)
print 'Socket na escuta %s:%s' % (HOST, PORT)
 
#Comunicacao com o cliente
while 1:
    #Espera uma conexao
    conn, addr = s.accept()
    print 'Conectado com ' + addr[0] + ':' + str(addr[1])
    
    #Envia mensagem de boas vindas ao cliente
    conn.send('Ola professor Paulo Matias, merecemos 10. E bem vindo ao nosso servidor!\n') #envio de dados
     
    #Conversa com o cliente ate fechar conexao
    while True:
         
        #Esperando dados
        data = conn.recv(1024)
        print 'Dados recebidos: ', data
        cmd = data.split()[0].lower()
        args = data.split()[1:]

        #Comandos
        if cmd.startswith("sayyourname"): #Fala o nome do host
        	conn.send(socket.gethostname() + '\n')
        elif cmd.startswith("echo"): #Repete o que recebeu
        	conn.send(" ".join(args) + '\n')
        elif cmd.startswith("close"): #Fecha conexao
            conn.close()
            print 'Conexao fechada.'
            break
        elif cmd.startswith("passaoarquivoaimano"): #Obedece a requisicao intimidadora e envia os dados contidos no arquivo solicitado
			filename = args[0]
			if os.path.exists(filename):
				f = open(filename, 'rb')
				dados_arquivo = f.read()
				conn.send(dados_arquivo + '\nArquivo terminado.\n')
				f.close()
			else:
				conn.send("Arquivo inexistente.")
        if not data: 
            break
    conn.close()
s.close()
