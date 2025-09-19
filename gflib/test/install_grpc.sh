#! /bin/bash
# this script is only needed if you are running your own ubuntu 20.04 vm without vagrant
curl -s --compressed "https://gt-cs6200.github.io/ppa/KEY.gpg" | sudo apt-key add -
sudo curl -s --compressed -o /etc/apt/sources.list.d/gt-cs6200.list "https://gt-cs6200.github.io/ppa/gt-cs6200.list"
sudo apt-get update
sudo apt-get install -y build-essential git zip unzip software-properties-common python3-pip python3-dev gcc-multilib valgrind portmap rpcbind libcurl4-openssl-dev bzip2 libssl-dev llvm net-tools libtool pkg-config grpc-cs6200 protobuf-cs6200
