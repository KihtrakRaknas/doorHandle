from bt_proximity import BluetoothRSSI
import time
import sys, getopt
import requests_async as requests
import RPi.GPIO as gpio  # https://pypi.python.org/pypi/RPi.GPIO more info
import atexit
import asyncio
import threading
from flask import Flask, request
app = Flask(__name__)


# iphone 13 pro: 'F8:C3:CC:9C:C9:6C'


motor_lock = asyncio.Lock()

notibot_project = ''
password = ''

async def main():
    BT_ADDR = ''
    try:
        opts, args = getopt.getopt(sys.argv[1:], "hb:n:p:", ["bluetoothaddress=", "notibotproject=", "password="])
    except getopt.GetoptError:
        print('USAGE: main.py -b <bluetoothaddress> [-n <notibotproject>] [-p <password>]')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('USAGE: main.py -b <bluetoothaddress> [-n <notibotproject>] [-p <password>]')
            sys.exit()
        elif opt in ("-b", "--bluetoothaddress"):
            BT_ADDR = arg
        elif opt in ("-n", "--notibotproject"):
            global notibot_project
            notibot_project = arg
        elif opt in ("-p", "--password"):
            global password
            password = arg
    if BT_ADDR == '':
        print('USAGE: main.py -b <bluetoothaddress>')
        sys.exit()

    global loop
    loop = asyncio.get_event_loop()
    set_up_motor()
    t1 = threading.Thread(target=server)
    t1.start()
    # asyncio.create_task(open_door())
    # await asyncio.sleep(1000)
    btrssi = BluetoothRSSI(addr=BT_ADDR)
    old_rssi = None
    old_rssis = []
    while True:
        rssi = btrssi.request_rssi()
        print(rssi)
        if rssi is None:
            if not (old_rssi is None):
                old_rssi = None
                old_rssis = [-50]*100
                # loop = asyncio.get_event_loop()
                asyncio.create_task(notif_call("phone%20lost"))
        else:
            rssi = rssi[0]

            old_rssis.append(rssi)
            if len(old_rssis) > 100:
                old_rssis.pop(0)

            if old_rssi is None:
                old_rssi = rssi
                asyncio.create_task(notif_call("phone%20detected"))
            else:
                print(str(all(-20 <= el < 0 for el in (old_rssis[-5:]))) + " & " + str(not all(-40 <= el <= 0 for el in (old_rssis[:90]))))
                if all(-20 <= el < 0 for el in (old_rssis[-5:])) and not all(-40 <= el <= 0 for el in (old_rssis[:90])):
                    asyncio.create_task(open_door())
        await asyncio.sleep(1)


async def open_door():
    print("open door called")
    if motor_lock.locked():
        return
    async with motor_lock:
        asyncio.create_task(notif_call("open%20door"))
        gpio.output(25, True) # Stop the motor from sleeping
        gpio.output(23, False) # Set the direction

        StepCounter = 0
        WaitTime = 0.0005
        Steps = 3500
        while StepCounter < Steps:
            # turning the gpio on and off tells the easy driver to take one step
            gpio.output(24, True)
            gpio.output(24, False)
            StepCounter += 1

            # Wait before taking the next step...this controls rotation speed
            time.sleep(WaitTime)
            # await asyncio.sleep(WaitTime)

        await asyncio.sleep(15)

        gpio.output(25, False)  # Motor goes back to sleeping
        asyncio.create_task(notif_call("close%20door"))


def server():
    @app.route('/webhook', methods=['GET', 'POST'])
    def respond():
        print("webhook called");
        if password != "" and request.json["password"] != password:
            return 'Invalid Password';
        asyncio.run_coroutine_threadsafe(open_door(), loop)
        return 'Done'

    from waitress import serve
    serve(app, host="0.0.0.0", port=8080)
    # app.run()


async def notif_call(str):
    if notibot_project != '':
        await requests.get('https://n.kihtrak.com/?project='+notibot_project+'&title='+str)


def set_up_motor():
    # use the broadcom layout for the gpio
    gpio.setmode(gpio.BCM)
    # GPIO23 = Direction
    # GPIO24 = Step
    # GPIO25 = SLEEP
    gpio.setup(23, gpio.OUT)
    gpio.setup(24, gpio.OUT)
    gpio.setup(25, gpio.OUT)

    gpio.output(25, False) # Make the motor sleep


def exit_handler():
    gpio.cleanup()


atexit.register(exit_handler)

if __name__ == '__main__':
    asyncio.run(main())
