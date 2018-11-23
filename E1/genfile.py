#Gerador de arquivo grande

f = open("arquivogrande", 'w')

for i in range(50000):
	f.write(1024 * 'A')

f.close()
