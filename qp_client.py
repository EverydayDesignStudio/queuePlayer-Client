
# Python libraries for Queue Player Software
#import keyboard
#from pynput.keyboard import Key
import copy
import threading
from threading import Timer
import time
import math
import requests
import requests.exceptions
import socketio
import json
import subprocess

import spotipy
import spotipy.util as util
import spotipy.oauth2 as oauth2
from spotipy.exceptions import SpotifyException

import sys
import os

# ----------------------------------------------------------
# Python libraries for Queue Player Hardware
import board
import neopixel
import RPi.GPIO as GPIO
import busio
import adafruit_ads1x15.ads1015 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

#Setup for potentiometer and piezo ADC channels
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1015(i2c)
chan_piezo = AnalogIn(ads, ADS.P1)  #piezo connected to pin A0
chan_pot = AnalogIn(ads, ADS.P0) #potentiometer connected to pin A1

#Variables to tune and adjust piezo sensitivity
# THRESHOLD = 0.8  # Adjust this value based on your piezo sensitivity
# DEBOUNCE_TIME = 0.1  # Adjust this value based on min. time needed between consecutive taps
#THRESHOLD = 0.5  # Adjust this value based on your piezo sensitivity
#DEBOUNCE_TIME = 0.1  # Adjust this value based on min. time needed between consecutive taps

#Neopixel Setup for strip and ring light
pixel_pin1 = board.D12 # the pin to which the LED strip is connected to
pixel_pin2 = board.D10 # the pin to which the ring light is connected to
num_pixels = 160 # this specifies the TOTAL number of pixels (should be a multiple of 12. ie. 12, 24, 36, 48 etc)
num_ring_pixels = 16
ORDER = neopixel.GRBW # set the color type of the neopixel
ledSegment = 36 # number of LEDs in a single segment
ledArray = [[[0 for i in range(4)] for j in range(ledSegment)] for z in range(4)] #the array which stores the pixel information

# #Create and initiate neopixel objects
pixels = neopixel.NeoPixel(pixel_pin1, num_pixels, brightness=255, auto_write=False, pixel_order=ORDER)
ring_pixels = neopixel.NeoPixel(pixel_pin2, num_ring_pixels, brightness = 10, auto_write = False, pixel_order=ORDER)

#Indicator Light Setup
GPIO.setup(23,GPIO.OUT)
GPIO.setup(24,GPIO.OUT)
GPIO.setup(25,GPIO.OUT)


#Tap Sensor Setup
channel = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(channel, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)

# ----------------------------------------------------------

YELLOW = (150, 75, 0, 0)
GREEN = (190, 210, 5, 5)
VIOLET = (150, 40, 215, 0)
ORANGE = (200, 45, 0, 0)

###########################################
###### Edit the ClientID accordingly ######
###########################################
clientID = 2
clientColor = (0, 0, 0, 0)

### Spotify Objects
sp = None                  # Spotipy Object
spToken = None             # Spotify Authentication Token
client_id = None
client_secret = None
spotify_username = None
device_id = None           # raspberry pi's device ID that is linked to the Spotify account
spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing, user-read-playback-state'
# spotify_redirect_uri = 'http://localhost:8000/callback'
spotify_redirect_uri = 'https://example.com/callback/'

# Global check variables
# These flags indicate:
bpmTimer = None          # a timer to keep checking for new incoming BPMs for every n seconds (by default, n=2)
isActive = False         # a flag to indicate if the client is active (ready to read new tap and play music)
isMusicPlaying = False   # whether a song is currently being played
isFadingToBlack = False  # lights for the queue and the ring will go out when the power is off
serverConnCheck = False  # check the server connection
isEarlyTransition = False # when receiving the broadcast msg before finishing the song -- need fast transition (fade-out, fade-in)

lightInfo = None
ringLightColor = (0, 0, 0, 0)
updateQueueLight = False   # a flag to update the queue lights
clientStates = []        # shows the status of all four clients (e.g., [True, True, False, False])

# BPM function variables
bpmAdded=0               # default base BPM to start with
tapCount=0               # the number of taps detected
tapInterval=3            # if no more tap is detected within 3 seconds, stop recording and calculate a new BPM
msFirstTap=0             # timestamp of the first detected tap
msLastTap=0              # timestamp of the last entered tap

# Server Variable
baseUrl="https://qp-master-server.herokuapp.com/"

# Global volume variables
prevVolume = 0            # previous value for volume
currVolume = 0            # current value for volume
refVolume = 0
fadingVolumeFlag = False

# Lights function variables
colorArrBefore=[(0,0,0,0)]*144    # indicates four queue colors for the 'current' state
colorArrAfter=[0]*144             # indicates four queue colors for the 'next' state

# Track Information
currTrackID=''
currTrackInfo = None
currBPM = 0
isBPMChanged = False
currCluster = None       # the current song's cluster in the DB

# Local timer variables for song end check
startTrackTimestamp = None
totalTrackTime = None
elapsedTrackTime = None

# A placeholder variable for the information about user’s current playback (song)
# https://spotipy.readthedocs.io/en/2.12.0/?highlight=current_playback#spotipy.client.Spotify.current_playback
playback=None

#fail-safe recovery
retry = 0
RETRY_MAX = 5

# Wrapper function for socket connection
def socketConnection():
    connected = False
    while not connected:
        try:
            sio.connect('https://qp-master-server.herokuapp.com/')
            print("Socket established")
            connected = True
        except Exception as ex:
            print("Failed to establish initial connnection to server:", type(ex).__name__)
            time.sleep(2)


def compareDeviceID():
    global sp, device_id

    print("  Comparing device IDs.")
    devices = None
    device_id_tmp = ''

    try:
        devices = sp.devices()
        print("@@ devices: ")
        print(devices)
        if (len(devices['devices']) > 0):
            device_id_tmp = devices['devices'][0]['id']

    except Exception as e:
        print(f"An error occurred while looking up the active devices: {str(e)}")
        time.sleep(2)

    return device_id_tmp == device_id


# Function to restart spotifyd -- checking the device connection
def restart_spotifyd():
    global retry, RETRY_MAX

    while True:
        try:
            print("Device not found. Reconnecting to Spotify...")
            subprocess.run(["sudo", "pkill", "spotifyd"]) # Kill existing spotifyd processes
            subprocess.run(["/home/pi/spotifyd", "--no-daemon", "--config-path", "/home/pi/.config/spotifyd/spotifyd.conf"]) # Restart spotifyd (check if this is the correct path)
            time.sleep(5)  # Wait for Spotifyd to restart

            deviceCheck = compareDeviceID()

        except Exception as e:
            print(f"An error occurred while restarting Spotifyd: {str(e)}")
            time.sleep(2)

        if (not deviceCheck):
            print("$$ retrying.. {}".format(retry))
            retry += 1

        else:
            break

        if (retry >= RETRY_MAX):
            print("!! retry max reached..")
            break
            # restart_script()

def restart_script():
    # Add any cleanup or state reset logic here
    time.sleep(5)  # Optional delay before restarting to avoid immediate restart loop
    print("Restarting the script...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

# acquires an authenticated spotify token
def getSpotifyAuthToken():
    global sp, spotify_username, client_id, client_secret, spotify_redirect_uri, spotify_scope, spToken

    print("Acquiring a Spotify Token..")
    spToken = util.prompt_for_user_token(username=spotify_username, scope=spotify_scope, client_id = client_id, client_secret = client_secret, redirect_uri = spotify_redirect_uri)
    sp = spotipy.Spotify(auth=spToken)

# returns a fresh token
def refreshSpotifyAuthToken():
    global sp, spotify_username, client_id, client_secret, spotify_redirect_uri, spotify_scope, spToken

    print("Refreshing a Spotify Token..")
    cache_path = ".cache-" + spotify_username
    sp_oauth = oauth2.SpotifyOAuth(client_id, client_secret, spotify_redirect_uri, scope=spotify_scope, cache_path=cache_path)
    token_info = sp_oauth.get_cached_token()
    spToken = token_info['access_token']
    sp = spotipy.Spotify(auth=spToken)


# ----------------------------------------------------------
# Section 1: Client State Control

def setClientActive():
    global clientID
    setClientActive=requests.post(baseUrl+"setClientActive", json={"clientID":clientID})

def setClientInactive():
    global clientID
    setClientInactive=requests.post(baseUrl+"setClientInactive", json={"clientID":clientID})

# Controls the potentiometer for volume and active/inactive state
def potController():
    global sp, isActive, prevVolume, currVolume, isMusicPlaying, currTrackID, elapsedTrackTime, serverConnCheck, isFadingToBlack, device_id, clientStates, fadingVolumeFlag

    #Voltage variables
    window_size = 5
    voltage_readings = [0] * window_size  # Initialize with zeros

    while True:
    # Inside your main loop where you read the potentiometer voltage
        try:
            # Read potentiometer voltage
            current_voltage = chan_pot.voltage

            # Update running average readings
            voltage_readings.append(current_voltage)

            # when QP is first turned on, wait a few more readings
            if (len(voltage_readings) < window_size):
                continue;
            elif (len(voltage_readings) > window_size):
                voltage_readings.pop(0)  # Remove the oldest reading

            # Calculate a running average
            filtered_voltage = running_average(voltage_readings)
            # filtered_voltage = current_voltage
            # print(filtered_voltage)

            # The voltage is lower than the 'active' threshold. The client is now 'inactive'.
            #  (1) pause the playback for this client
            #  (2) notify the server
            #  (3) turn the queue lights off
            #  (4) turn the ring light off
            if filtered_voltage < 0.03:
                # double-check if the song is being played and the BPM is 'tappable'
                if isActive:
                    # set the flags off so it's not playing the song or detecting any BPM taps
                    isActive=False

                    # reset tap variables
                    bpmAdded = 0
                    msLastTap = 0
                    tapCount = 0

                    # notify the server that this client is off
                    setClientInactive()
                    print("Potentiometer is turned OFF.")
                    print("Client is set Inactive")

                    # turn the queue and ring lights off
                    isFadingToBlack = True

            # The client becomes 'active',
            # (1) should start listening to new bpm (set isActive to True)
            # (2) should be connected to the server
                ### TODO: check these thesholds
            elif filtered_voltage > 0.1 and not isActive and serverConnCheck:
                # notify the server that this client is 'active'
                isActive = True
                setClientActive()
                print("Potentiometer is turned ON.")
                print("Client is set Active")

            # This is when a client is recovered from a disconnection or device not found exception
            elif filtered_voltage > 0.1 and serverConnCheck and len(clientStates) == 4 and not clientStates[clientID-1]:
                # notify the server that this client is 'active'
                setClientActive()
                print("Current client states: ", clientStates)
                print("Client connection is recovered. Request the server to set this client Active")

            # If a song is being played and the pot value changes, this indicates the volume change.
            #     *** have this as a seperate thread maybe just to have better code modularity, no point being here anyways
            if isActive:
                # pause reading the volume when the volume is fading in or out
                if (not fadingVolumeFlag):
                    # set to a new volume (read the pot) -- prevent sudden volume change
                    currVolume = int(map_to_volume(filtered_voltage))

                    # only update the volume when the new voltage is moved more than a certain threshold
                    if(abs(prevVolume-currVolume) >= 5):
                        prevVolume = currVolume

                        try:
                            devices = sp.devices()['devices']
                            print("potController Changing Volume")
                            print("Current devices: ", devices)
                            sp.volume(currVolume, device_id)

                        # Restart spotifyd with credentials if device is not found
                        except spotipy.exceptions.SpotifyException as e:
                            # Check for "device not found" error
                            if e.http_status == 404 and "Device not found" in str(e):
                                print("Device not found. [in PotController when changing volume] Restarting spotifyd...")

                                restart_spotifyd()

                                print("Disconnecting from server...")
                                sio.disconnect()
                                time.sleep(2)
                                print("Reconnecting to server...")
                                #sio.connect('https://qp-master-server.herokuapp.com/')
                                socketConnection()
                            elif e.http_status == 401:
                                print("Spotify Token Expired in potController when changing volume")
                                refreshSpotifyAuthToken()

                        except requests.exceptions.ConnectTimeout:
                            print("Connection timeout while changing volume")
                            print("Disconnecting from server...")
                            sio.disconnect()
                            time.sleep(2)
                            print("Reconnecting to server...")
                            #sio.connect('https://qp-master-server.herokuapp.com/')
                            socketConnection()

                        except requests.exceptions.ReadTimeout:
                            print("Read timeout while changing volume")

                            print("Disconnecting from server...")
                            sio.disconnect()
                            time.sleep(2)

                            refreshSpotifyAuthToken()

                            print("Reconnecting to server...")
                            #sio.connect('https://qp-master-server.herokuapp.com/')
                            socketConnection()

                        except Exception as e:
                            print(f"An error occurred while changing volume: {str(e)}")
                            time.sleep(2)

        # this is only for testing
        except KeyboardInterrupt:
            print("Interrupted by Keyboard, script terminated")

            sio.disconnect()
            time.sleep(2)
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()


# ----------------------------------------------------------

# ----------------------------------------------------------
# Section 2: Client->Server + Client->Spotify Controls

def pushBPMToQueue(bpm):
    songToBeQueued=requests.post(baseUrl+"getTrackToQueue", json={"bpm":bpm, "clientID":clientID, "cln":currCluster})

# read the tap once, record the timestamp
# increase or reset the tap count, depending on the interval
def TapBPM():
    global tapCount, msFirstTap, msLastTap, bpmAdded

    msCurr=int(time.time()*1000)
    if(msCurr-msLastTap > 1000*2):
        tapCount = 0

    if(tapCount == 0):
        print ("  # First tap")
        msFirstTap = msCurr
        tapCount = 1
    else:
        if msCurr-msFirstTap > 0:
            bpmAvg= 60000 * tapCount / (msCurr-msFirstTap)
            bpmAdded=round(round(bpmAvg*100)/100)
        tapCount+=1
        print ("  # Next tap {}".format(tapCount))

    msLastTap=msCurr

# There is a new BPM that just came in, so notify the server to either play a song or add a song to the queue
def tapController():
    global isActive, bpmAdded, msLastTap, tapCount, tapInterval

    while True:

        msCurr = int(time.time()*1000)

        try:
            # the last tap has happened more than 2 seconds ago -- finish recording
            if msCurr-msLastTap > 1000*tapInterval and bpmAdded > 0:
                print("   # LastTap Detected. BPM: {}".format(bpmAdded))
                # notify the server accordingly,
                if isActive:
                    pushBPMToQueue(bpmAdded)

                # reset the variables
                bpmAdded = 0
                msLastTap = 0
                tapCount = 0

        except KeyboardInterrupt:
            print("Interrupted by Keyboard, script terminated")
            sio.disconnect()
            time.sleep(2)
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

        time.sleep(2)

# A worker function to detect and update the tap signals
# This will only run once whenever the tap sensor receives a signal
def tapSensor(channel):
    global isActive, bpmTimer

    if isActive:
        try:
            if GPIO.input(channel):
                print ("Tap")
                TapBPM()
        except KeyboardInterrupt:
            print("Interrupted by Keyboard, script terminated")
            sio.disconnect()
            time.sleep(2)
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

GPIO.add_event_detect(channel, GPIO.BOTH, bouncetime=1)  # let us know when the pin goes HIGH or LOW
GPIO.add_event_callback(channel, tapSensor)  # assign function to GPIO PIN, Run function on change


def map_to_volume(input_value):
    input_min = 0.01 #adjust this value to value right after pot clicks on
    input_max = 4.0
    output_min = 0.0
    output_max = 100.0

    volume = ((input_value - input_min) / (input_max - input_min)) * (output_max - output_min) + output_min
    if volume > 100.0:
        return 100.0
    elif volume < 0.0:
        return 0.0
    else:
        return volume

# ----------------------------------------------------------
# Section 3: Volume Control

# calculate a running average
def running_average(values):
    return sum(values) / len(values)


def fadeOutVolume(halt = False):
    global sp, currVolume, refVolume, device_id, fadingVolumeFlag

    refVolume = currVolume

    while (refVolume > 0):
        refVolume = int(refVolume / 1.5)

        # Ensure volume goes to 0
        if refVolume < 1:
            refVolume = 0

        try:
            sp.volume(refVolume, device_id=device_id)

        # Restart spotifyd with credentials if device is not found
        except spotipy.exceptions.SpotifyException as e:
            # Check for "device not found" error
            if e.http_status == 404 and "Device not found" in str(e):
                print("Device not found when [fading out volume]. Restarting spotifyd...")

                restart_spotifyd()

                print("Disconnecting from server...")
                sio.disconnect()
                time.sleep(2)
                print("Reconnecting to server...")
                #sio.connect('https://qp-master-server.herokuapp.com/')
                socketConnection()
            elif e.http_status == 401:
                print("Spotify Token Expired in [fading out volume]")
                refreshSpotifyAuthToken()

        except requests.exceptions.ConnectTimeout:
            print("Connection timeout while [fading out volume]")
            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

        except requests.exceptions.ReadTimeout:
            print("Read timeout while [fading out volume]")

            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)

            refreshSpotifyAuthToken()

            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

        except Exception as e:
            print(f"An error occurred while [fading out volume]: {str(e)}")
            time.sleep(2)

        # Delay to prevent hitting API rate limits and to make fade in smoother
        time.sleep(0.2)

    # halt for instant fade-out, fade-in for early transition
    if not halt:
        # remove the flag
        fadingVolumeFlag = False


def fadeInVolume():
    global sp, currVolume, refVolume, device_id, fadingVolumeFlag

    refVolume = 0  # Start from volume 0

    while refVolume < currVolume:

        # Increment volume
        refVolume = int(refVolume * 1.5 + 1)

        # Ensure volume does not exceed target
        if refVolume > currVolume:
            refVolume = currVolume

        try:
            sp.volume(refVolume, device_id=device_id)

        # Restart spotifyd with credentials if device is not found
        except spotipy.exceptions.SpotifyException as e:
            # Check for "device not found" error
            if e.http_status == 404 and "Device not found" in str(e):
                print("Device not found when [fading in volume]. Restarting spotifyd...")

                restart_spotifyd()

                print("Disconnecting from server...")
                sio.disconnect()
                time.sleep(2)
                print("Reconnecting to server...")
                #sio.connect('https://qp-master-server.herokuapp.com/')
                socketConnection()
            elif e.http_status == 401:
                print("Spotify Token Expired in [fading in volume]")
                refreshSpotifyAuthToken()

        except requests.exceptions.ConnectTimeout:
            print("Connection timeout while [fading in volume]")
            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

        except requests.exceptions.ReadTimeout:
            print("Read timeout while [fading in volume]")

            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)

            refreshSpotifyAuthToken()

            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

        except Exception as e:
            print(f"An error occurred while [fading in volume]: {str(e)}")
            time.sleep(2)

        # Delay to prevent hitting API rate limits and to make fade in smoother
        time.sleep(0.2)

    # remove the flag
    fadingVolumeFlag = False


# ----------------------------------------------------------
# Section 4: NeoPixel & Ring Light Control

def interpolate_rgbw(start_rgbw, end_rgbw, steps):
    r1, g1, b1, w1 = start_rgbw
    r2, g2, b2, w2 = end_rgbw

    delta_r = (r2 - r1) / steps
    delta_g = (g2 - g1) / steps
    delta_b = (b2 - b1) / steps
    delta_w = (w2 - w1) / steps

    results = []
    for i in range(steps + 1):
        r = int(r1 + delta_r * i)
        g = int(g1 + delta_g * i)
        b = int(b1 + delta_b * i)
        w = int(w1 + delta_w * i)
        results.append((r, g, b, w))

    return results


def colorArrayBuilder(lightInfo):
    global colorArrBefore, colorArrAfter, pixels
    n = 0
    print("inside colorArrayBuilder")
    print(pixels[0])

    for queueLight in lightInfo:
        print("for loop enters")
        colors = lightInfo[queueLight]["colors"]
        isNewBPM = lightInfo[queueLight]["isNewBPM"]

        ### TODO: reverse the brightness?
        # Check if "rotate" is True for the current ring
        if isNewBPM:
            dim_brightness = 50  # Adjust the dim brightness as needed
        else:
            dim_brightness = 255  # Full brightness for non-rotating rings

        divs = int(36 / len(colors))
        rgb_vals = []
        for i in colors:
            rgb_vals.append((colors[i]["r"], colors[i]["g"], colors[i]["b"], colors[i]["w"]))
        for i in range(len(rgb_vals)):
            colorArrAfter[n:n+divs] = interpolate_rgbw(rgb_vals[i], rgb_vals[(i+1) % len(rgb_vals)], divs)

            if isNewBPM:
                for j in range(n, n + divs):
                    colorArrAfter[j] = tuple(int(val * dim_brightness / 255) for val in colorArrAfter[j])

            n += divs

    # Check if color array is different to trigger fade in and out
    if colorArrBefore != colorArrAfter:
        print("if enters")
        # Define the maximum brightness value
        max_brightness = 255
        fade_duration = 0.15 # Adjust the fade duration as desired

        # Calculate the number of steps based on the fade duration and delay
        num_steps = int(fade_duration / 0.01)

        # Fade-out effect
        if not (pixels[0] == [0,0,0,0]):
            print("fade out")
            for step in range(num_steps, -1, -1):
                brightness = int(step * max_brightness / num_steps)
                for i in range(144):
                    pixels[i] = colorArrBefore[i]
                pixels.brightness = brightness / max_brightness
                pixels.show()
                time.sleep(0.01)

        # Fade-in effect
        print("fade in")
        for step in range(num_steps + 1):
            brightness = int(step * max_brightness / num_steps)
            for i in range(144):
                pixels[i] = colorArrAfter[i]
            pixels.brightness = brightness / max_brightness
            pixels.show()
            time.sleep(0.01)

        colorArrBefore = copy.deepcopy(colorArrAfter)


def fadeToBlack():
    global pixels # Make sure 'pixels' is a global variable
    global colorArrBefore

    # Define the maximum brightness value
    max_brightness = 255
    fade_duration = 0.05  # Adjust the fade duration as desired

    # Calculate the number of steps based 5on the fade duration and delay
    num_steps = int(fade_duration / 0.01)

    # Fade-out effect
    #while not(pixels[0]==[0,0,0,0]):
    for step in range(num_steps, -1, -1):
        brightness = int(step * max_brightness / num_steps)

        # Set the color for all pixels
        for i in range(144):
            pixels[i] = colorArrBefore[i]

        # Update the brightness for all pixels
        pixels.brightness = brightness / max_brightness


        # Display the updated pixels
        pixels.show()
        print("in fade to black function")

        # Add a slightly longer delay for a slower fade-off
        time.sleep(0.01)
    pixels[0] = [0,0,0,0]


def queueLightController():
    global lightInfo,updateQueueLight

    while True:
        try:
            if (updateQueueLight):
                colorArrayBuilder(lightInfo)
                updateQueueLight=False
        except TimeoutError:
            print("Timeout Error in queueLightController")

            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()


# the ring light indicates the last client tapped
def ringLightController():
    global lightInfo, pixels, ringLightColor, isActive, isBPMChanged, currBPM

    while True:
        try:
            # flash the ring light when the QP is active
            if(isActive):
                # calculate the beat interval only once when the bpm changes
                if (isBPMChanged):
                    # Calculate the time interval between beats
                    interval = 60 / currBPM
                    beat_interval = 60 / (currBPM * 2.5)
                    isBPMChanged = False

                # ring lights on
                for i in range(144, 160):
                    pixels[i] = ringLightColor
                pixels.show()
                time.sleep(beat_interval)

                # ring lights off
                for i in range(144, 160):
                    pixels[i] = (0, 0, 0, 0)
                pixels.show()
                time.sleep(beat_interval)

        except TimeoutError:
            print("Timeout Error in ringLightController")

            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

def indicatorLightController():
    global clientID, clientStates

    while True:
        try:
            # Client 1 - Green, Violet, Orange
            if(clientID == 1):
                if(len(clientStates) > 0 and clientStates[1] == True): #Green QP
                    GPIO.output(23,GPIO.HIGH)
                else:
                    GPIO.output(23,GPIO.LOW)

                if(len(clientStates) > 0 and clientStates[2] == True): #Violet QP
                    GPIO.output(24,GPIO.HIGH)
                else:
                    GPIO.output(24,GPIO.LOW)

                if(len(clientStates) > 0 and clientStates[3] == True): #Orange QP
                    GPIO.output(25,GPIO.HIGH)
                else:
                    GPIO.output(25,GPIO.LOW)

            # Client 2 - Yellow, Violet, Orange
            elif(clientID == 2):
                if(len(clientStates) > 0 and clientStates[0] == True): #Yellow QP
                    GPIO.output(23,GPIO.HIGH)
                else:
                    GPIO.output(23,GPIO.LOW)

                if(len(clientStates) > 0 and clientStates[2] == True): #Violet QP
                    GPIO.output(24,GPIO.HIGH)
                else:
                    GPIO.output(24,GPIO.LOW)

                if(len(clientStates) > 0 and clientStates[3] == True): #Orange QP
                    GPIO.output(25,GPIO.HIGH)
                else:
                    GPIO.output(25,GPIO.LOW)

            # Client 3 - Yellow, Green, Orange
            elif(clientID == 3):
                if(len(clientStates) > 0 and clientStates[0] == True): #Yellow QP
                    GPIO.output(23,GPIO.HIGH)
                else:
                    GPIO.output(23,GPIO.LOW)

                if(len(clientStates) > 0 and clientStates[1] == True): #Green QP
                    GPIO.output(24,GPIO.HIGH)
                else:
                    GPIO.output(24,GPIO.LOW)

                if(len(clientStates) > 0 and clientStates[3] == True): #Orange QP
                    GPIO.output(25,GPIO.HIGH)
                else:
                    GPIO.output(25,GPIO.LOW)

            # Client 4 - Yellow, Green, Violet
            elif(clientID == 4):
                if(len(clientStates) > 0 and clientStates[0] == True): #Yellow QP
                    GPIO.output(23,GPIO.HIGH)
                else:
                    GPIO.output(23,GPIO.LOW)

                if(len(clientStates) > 0 and clientStates[1] == True): #Green QP
                    GPIO.output(24,GPIO.HIGH)
                else:
                    GPIO.output(24,GPIO.LOW)

                if(len(clientStates) > 0 and clientStates[2] == True): #Violet QP
                    GPIO.output(25,GPIO.HIGH)
                else:
                    GPIO.output(25,GPIO.LOW)

        except TimeoutError:
            print("Timeout Error in infiniteloop6")

            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

def fadeoutController():
    global isFadingToBlack

    while True:
        try:
            if(isFadingToBlack):
                print("fading to black")
                fadeToBlack()
                isFadingToBlack = False
        except TimeoutError:
            print("Timeout Error in fadeoutController")

            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

# ----------------------------------------------------------
# Section 5: Music Controls

# A wrapper function to save information for cross-checking if the next song coming in is a new song
# This prevents the same song from playing repeatedly
def notifyTrackFinished(trackID):
    global isMusicPlaying, currCluster

    isMusicPlaying = False
    continueSong = requests.get(baseUrl+"trackFinished", json={"clientID":clientID, "trackID":trackID, "cln":currCluster})

# Start a local manual timer for the duration of the song to identify the end of the song
# This will avoid rate limit issues from SpotifyAPI
# (1) Check if the client is playing any song, if not, continue checking
# (2)⁠ Check whether a duration should be set for the currently playing song (True by default)
# (3)⁠ ⁠⁠When checking the duration, fetch the duration of the song from the SpotifyAPI,
#      set the durationCheck to false as for the song's duration is now figured out
# (4)⁠ Update related variables
# (5)⁠ If the client is joining others, seekCheck is True -- modify the local timer with a simple calculation
# (6)⁠ ⁠⁠Since now the duration has been set and the timer has started with durationCheck as False, continue
# (7)⁠ Check if the song is being repeated by checking the song's ID
# (8)⁠ Check if the timer is within 10 seconds of the song's end.
#      If so, start the fade-out and the song ends
#      Then, request the server for the next song —> trackFinished
def playSongController():
    global sp, device_id
    global currTrackID, prevVolume, currVolume, isMusicPlaying, isActive, fadingVolumeFlag
    global startTrackTimestamp, totalTrackTime, elapsedTrackTime, isEarlyTransition

    while True:
        try:
            # QP is OFF
            if not isActive:
                if (isMusicPlaying):
                    isMusicPlaying=False

                    fadingVolumeFlag = True
                    fadeOutVolume()
                    prevVolume = 0
                    currVolume = 0

                    sp.pause_playback(device_id=device_id)

                # even if the music is not playing, clean up the variables
                else:
                    fadingVolumeFlag = False
                    prevVolume = 0
                    currVolume = 0

            # QP is ON
            else:
                # but if no music is playing, play the music
                if not isMusicPlaying and currTrackID != '':
                    elapsed_time = (time.time() - startTrackTimestamp) * 1000
                    elapsedTrackTime = int(elapsed_time)

                    devices = sp.devices()['devices']
                    print("PlaySong.")
                    print("Current devices: ", devices)
                    trackURIs = ["spotify:track:"+currTrackID]
                    sp.start_playback(device_id=device_id, uris=trackURIs, position_ms=elapsedTrackTime)
                    fadingVolumeFlag = True
                    fadeInVolume()

                    # indicate the song is now playing
                    isMusicPlaying=True

                # if music is playing,
                else:
                    elapsed_time = (time.time() - startTrackTimestamp) * 1000
                    elapsedTrackTime = int(elapsed_time)

                    # when the server forces you to skip to the next song,
                    if (isEarlyTransition):
                        fadingVolumeFlag = True
                        fadeOutVolume(True)
                        trackURIs = ["spotify:track:"+currTrackID]
                        sp.start_playback(device_id=device_id, uris=trackURIs, position_ms=elapsedTrackTime)
                        fadeInVolume()

                    else:
                        # when the song ends, notify the server and start fading out
                        if elapsed_time > totalTrackTime:
                            print("Song has ended")
                            fadingVolumeFlag = True
                            fadeOutVolume(True)
                            notifyTrackFinished(currTrackID)

        except spotipy.exceptions.SpotifyException as e:
            # Check for "device not found" error
            if e.http_status == 404 and "Device not found" in str(e):
                print("Device not found. [in PlaySongController] Restarting spotifyd...")

                restart_spotifyd()

                print("Disconnecting from server...")
                sio.disconnect()
                time.sleep(2)
                print("Reconnecting to server...")
                #sio.connect('https://qp-master-server.herokuapp.com/')
                socketConnection()
            elif e.http_status == 401:
                print("Spotify Token Expired in PlaySongController when getting the current playback")
                refreshSpotifyAuthToken()

        except requests.exceptions.ConnectTimeout:
            print("Connection timeout [in PlaySongController]")
            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

        except requests.exceptions.ReadTimeout:
            print("Read timeout [in PlaySongController]")
            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)

            refreshSpotifyAuthToken()

            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

        except KeyboardInterrupt:
            print("Interrupted by Keyboard [in PlaySongController], script terminated")

            sio.disconnect()

            time.sleep(2)
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

        except TimeoutError:
            print("Timeout Error [in PlaySongController]")

            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()

# ----------------------------------------------------------
# Section 6: QueuePlayer Client Main

try:

    print("start of script")
    thread_TapSensor = threading.Thread(target=tapSensor(channel))
    thread_TapSensor.start()

    thread_PlaySong = threading.Thread(target=playSongController)
    thread_PlaySong.start()

    thread_Potentiometer = threading.Thread(target=potController)
    thread_Potentiometer.start()

    thread_TapController = threading.Thread(target=tapController)
    thread_TapController.start()

    thread_QueueLight = threading.Thread(target=queueLightController)
    thread_QueueLight.start()

    thread_RingLight = threading.Thread(target=ringLightController)
    thread_RingLight.start()

    thread_IndicatorLight = threading.Thread(target=indicatorLightController)
    thread_IndicatorLight.start()

    thread_Fadeout = threading.Thread(target=fadeoutController)
    thread_Fadeout.start()


    # ----------------------------------------------------------
    # Section 5: Socket Controls

    sio = socketio.Client()
    print("trying to connect")

    @sio.event
    def connect():
        global serverConnCheck, clientID, clientColor, sp, spToken
        global client_id, client_secret, spotify_username, device_id, spotify_scope, spotify_redirect_uri

        serverConnCheck = True
        print('Connected to server')
        sio.emit('connect_user', { "clientID": clientID } )

        if (clientID == 1):
            ### OLO5
            clientColor = YELLOW
            client_id='765cacd3b58f4f81a5a7b4efa4db02d2'
            client_secret='cb0ddbd96ee64caaa3d0bf59777f6871'
            spotify_username='n39su59fav4b7fmcm0cuwyv2w'
            device_id='fc0b6be2a96214b9a63fbf6d9584c2cde0a0cf8b'
        elif (clientID == 2):
            ### OLO4
            clientColor = GREEN
            client_id='aeeefb7f628b41d0b7f5581b668c27f4'
            client_secret='7a75e01c59f046888fa4b99fbafc4784'
            spotify_username='x8eug7lj2opi0in1gnvr8lfsz'
            device_id='651d47833f4c935fadd4a03e43cd5a4c3ec0d170' #raspberry pi ID
            #device_id = '4cb43e627ebaf5bbd05e96c943da16e6fac0a2c5' #web player ID
        elif (clientID == 3):
            ### OLO3
            clientColor = VIOLET
            client_id = 'd460c59699a54e309617458dd596228d'
            client_secret = '7655a37f76e54744ac55617e3e588358'
            spotify_username='qjczeruw4padtyh69nxeqzohi'
            device_id = '6b5d83a142591f256666bc28a3eccb56258c5dc7'
        elif (clientID == 4):
            ### OLO2
            clientColor = ORANGE
            client_id='bdfdc0993dcc4b9fbff8aac081cad246'
            client_secret='969f0ef8c11d49429e985aab6dd6ff0c'
            spotify_username='7w8j8bkw92mlnz5mwr3lou55g'
            #device_id='651d47833f4c935fadd4a03e43cd5a4c3ec0d170'
            #device_id = '217a37cc1f6f9c7937afbfa6f50424b7d937620f'
            device_id = '3946ec2b810ec4e30489b4704e9a695b1a64da26'

        # sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, scope=spotify_scope, username=spotify_username, requests_session=True, requests_timeout=None, open_browser=False))

        ### SPOTIFY AUTH
        try:
            refreshSpotifyAuthToken()
        except:
            getSpotifyAuthToken()

    @sio.event
    def disconnect():
        global serverConnCheck, isActive

        serverConnCheck = False
        isActive = False
        print('Disconnected from server')


    @sio.event
    def stateChange(data):
        global clientStates

        print("## State change message received.")
        json_data = json.loads(data) # incoming message is transformed into a JSON object
        print("    Previous client states: ", clientStates)
        clientStates = json_data["activeUsers"]
        print("    Current client states: ", clientStates)


    @sio.event
    def broadcast(data):
        global sp, spToken, clientStates
        global isMusicPlaying, isActive, lightInfo, currTrackInfo
        global currBPM, currTrackID, currCluster, ringLightColor, isBPMChanged
        global elapsedTrackTime, totalTrackTime, startTrackTimestamp, isEarlyTransition

        json_data = json.loads(data) # incoming message is transformed into a JSON object
        print("Server Sent the JSON:")
        print(json.dumps(json_data, indent = 2))

        clientStates = json_data["activeUsers"]
        print("    Current client states: ", clientStates)

        # track changes
        if (json_data["currentTrack"]["trackID"] != currTrackID):
            print("## New TrackID Received!")
            currTrackID = json_data["currentTrack"]["trackID"]
            currCluster = json_data["currentTrack"]["cluster_number"]

            if (currBPM != json_data["currentTrack"]["bpm"]):
                currBPM = json_data["currentTrack"]["bpm"]
                isBPMChanged = True

            # if the time remaining until the next song starts
            #       (the difference between broadcastTimestamp and startTrackTimestamp)
            #    is less (<) than the time remaining in the current song
            #       (totalTrackTime - elapsedTrackTime)
            # if true, it means the client is running behind, and an early transition to the next song is necessary.
            if (json_data["currentTrack"]["broadcastTimestamp"] - startTrackTimestamp < totalTrackTime - elapsedTrackTime):
                isEarlyTransition = True

            startTrackTimestamp = json_data["currentTrack"]["broadcastTimestamp"]
            lightInfo = json_data["lightInfo"]
            updateQueueLight = True

            # change the ring light only when the current track is added by tapping (by anyone)
            #    or the ring color is actually different -- this is for the clients who joins the queue
            #
            if (json_data["currentTrack"]["isNewBPM"] or ringLightColor != lightInfo["queueLight1"]["ringLight"]):
                ringLightColor = lightInfo["queueLight1"]["ringLight"]

                # verbose for testing
                clientX = 0
                if (ringLightColor == YELLOW):
                    clientX = 1
                elif (ringLightColor == GREEN):
                    clientX = 2
                elif (ringLightColor == VIOLET):
                    clientX = 3
                elif (ringLightColor == ORANGE):
                    clientX = 4
                print("##  This track is tapped by Client {}. Change the ring light.".format(clientX))

            try:
                currTrackInfo = sp.track(currTrackID)
                totalTrackTime = currTrackInfo['duration_ms']

            except requests.exceptions.ConnectTimeout:
                print("Connection timeout while requesting track info")
                print("Disconnecting from server...")
                sio.disconnect()
                time.sleep(2)
                print("Reconnecting to server...")
                #sio.connect('https://qp-master-server.herokuapp.com/')
                socketConnection()

            except requests.exceptions.ReadTimeout:
                print("Read timeout while requesting track info")

                print("Disconnecting from server...")
                sio.disconnect()
                time.sleep(2)

                refreshSpotifyAuthToken()

                print("Reconnecting to server...")
                #sio.connect('https://qp-master-server.herokuapp.com/')
                socketConnection()

            #Last Resort is to restart script
            # except requests.exceptions.ReadTimeout:
                # print("Minor Setback. Restarting the script...")
                # restart_script()

            # Restart spotifyd with credentials if device is not found
            except spotipy.exceptions.SpotifyException as e:
                # Check for "device not found" error
                if e.http_status == 404 and "Device not found" in str(e):
                    print("Device not found. [broadcast] Restarting spotifyd...")

                    restart_spotifyd()

                    print("Disconnecting from server...")
                    sio.disconnect()
                    time.sleep(2)
                    print("Reconnecting to server...")
                    #sio.connect('https://qp-master-server.herokuapp.com/')
                    socketConnection()
                elif e.http_status == 401:
                    print("Spotify Token Expired in broadcast")
                    refreshSpotifyAuthToken()

        else:
            print("## Same TrackID. I'm already on this track.")

        print("///////////////////////////////////////////////////////////////////////////////////////////////////////////")

    print("should be connected")
    #sio.connect('https://qp-master-server.herokuapp.com/')
    socketConnection()
    sio.wait()
except KeyboardInterrupt:
    print("Interrupted by Keyboard, script terminated")

    print("Disconnecting from server...")
    sio.disconnect()
    isMusicPlaying=False
    isActive=False
    time.sleep(2)
    print("Reconnecting to server...")
    socketConnection()
    #sio.connect('https://qp-master-server.herokuapp.com/')

# ----------------------------------------------------------
