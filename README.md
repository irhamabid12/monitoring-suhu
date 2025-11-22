DHT11
1. sudo apt update
2. sudo apt install python3-pip python3-dev python3-rpi.gpio
3. sudo pip3 install adafruit-blinka --break-system-packages
4. sudo pip3 install adafruit-circuitpython-dht --break-system-packages
5. sudo pip3 install websocket-client --break-system-packages

Enable One-Wire
1. sudo raspi-config
2. Interface Options
3. 1-Wire
4. sudo reboot

Sensor ds18b20
1. sudo pip3 install w1thermsensor --break-system-packages

install pm2
1. sudo apt update 
2. sudo apt install nodejs npm -y
3. sudo npm install -g pm2
6. sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u itkirsdsiot --hp /home/itkirsdsiot
7. pm2 start multids18b20.py --name ds18b20 --interpreter=python3
8. pm2 save
9. sudo reboot
