all: hexdump ./classes/edu/gatech/gios/MtgfTestClient.class

hexdump:hexdump.c
	$(CC) -o $@ $^

 ./classes/edu/gatech/gios/MtgfTestClient.class: ./src/edu/gatech/gios/MtgfTestClient.java
	javac -d ./classes/ ./src/edu/gatech/gios/MtgfTestClient.java
