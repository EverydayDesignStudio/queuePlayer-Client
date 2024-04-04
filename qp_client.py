
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

# Create a lock
spotify_lock = threading.Lock()

# Global check variables
# These flags indicate:
isQPON = False           # a flag represents the reading the potentiometer voltage
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
tapInterval=2            # if no more tap is detected within n seconds, stop recording and calculate a new BPM
msFirstTap=0             # timestamp of the first detected tap
msLastTap=0              # timestamp of the last entered tap

# Server Variable
baseUrl="https://qp-master-server.herokuapp.com/"

# Global volume variables
prevVolume = 0            # previous value for volume
currVolume = 0            # current value for volume
refVolume = 0             # placeholder for a temporary volume for fading in and out
fadingVolumeFlag = False
VOLTAGE_THRESHOLD = 0.03  # minimum threshold voltage to turn ON the QueuePlayer

# Lights function variables
colorArrBefore=[(0,0,0,0)]*144    # indicates four queue colors for the 'current' state
colorArrAfter=[0]*144             # indicates four queue colors for the 'next' state

# Track Information
currTrackID=''
currTrackInfo = None
currBPM = 0
isBPMChanged = False
currCluster = None       # the current song's cluster in the DB
currQueuedTrackIDs = []

# Local timer variables for song end check
startTrackTimestamp = -1
totalTrackTime = -1
elapsedTrackTime = -1
nextTrackRequested = False

# A placeholder variable for the information about user’s current playback (song)
# https://spotipy.readthedocs.io/en/2.12.0/?highlight=current_playback#spotipy.client.Spotify.current_playback
playback=None

#fail-safe recovery
retry_main = 0              # retry count before restarting the entire script
retry_connection = 0        # retry count for server connection timeout
retry_DNF = 0               # retry count for Device Not Found error
RETRY_MAX = 3
sleepTimeOnError = 2        # when there is an exception, pause for x seconds

### Verbose and flags for each thread to print lines for debugging
VERBOSE = True
FLAGS = 0
FLAG_PlaySongController = 1          # 00000001
FLAG_PotController = 2               # 00000010
FLAG_TapController = 4               # 00000100
FLAG_QueueLightController = 8        # 00001000
FLAG_RingLightController = 16        # 00010000
FLAG_IndicatorLightController = 32   # 00100000
FLAG_FadeOutController = 64          # 01000000
FLAG_SocketMessages = 128            # 10000000

### Set flags accordingly
FLAGS |= FLAG_SocketMessages         # Set flag for receiving the server messages
# FLAGS |= FLAG_QueueLightController   # Set flag for the queueLightController
# FLAGS |= FLAG_PlaySongController
# FLAGS |= FLAG_PotController
# FLAGS |= FLAG_TapController
# FLAGS |= FLAG_RingLightController
# FLAGS |= FLAG_IndicatorLightController
# FLAGS |= FLAG_FadeOutController

# Helper function to check if a flag is set
def isVerboseFlagSet(flag):
    global FLAGS
    return VERBOSE and (FLAGS & flag) != 0

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
            time.sleep(sleepTimeOnError)


def compareDeviceID():
    global sp, device_id

    print("  Comparing device IDs.")
    devices = None
    device_id_tmp = ''

    try:
        with spotify_lock:
            devices = sp.devices()
        print("@@ devices: ")
        print(devices)
        if (len(devices['devices']) > 0):
            device_id_tmp = devices['devices'][0]['id']

    except Exception as e:
        print(f"  !! An error occurred [in CompareDeviceID] while looking up the active devices: {str(e)}")
        time.sleep(sleepTimeOnError)
        raise

    return device_id_tmp == device_id


def retryServerConnection():
    global retry_connection

    if (retry_connection < RETRY_MAX):
        try:
            print ("  !! RETRY MAX reached. Try reconnecting to the server..")
            sio.disconnect()
            time.sleep(sleepTimeOnError)
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()
        except:
            retry_connection += 1
            raise

        retry_connection = 0

    else:
        retry_connection = 0
        restart_script()

def restart_script():
    global retry_main

    print(" ## Restart Script Called.")

    if (retry_main >= RETRY_MAX):
        print(" ## Retry_main count (", retry_main ,") reached RETRY_MAX of ", RETRY_MAX)
        print(" ## Restarting the qp_client.py..")

        # Add any cleanup or state reset logic here
        sio.disconnect()
        time.sleep(3)  # Optional delay before restarting to avoid immediate restart loop
        print("Restarting the script...")
        python = sys.executable
        os.execl(python, python, *sys.argv)

        ### Option 2:
        # python_executable = sys.executable
        # script_file = __file__
        # subprocess.call([python_executable, script_file])
        # sys.exit()

    else:
        retry_main += 1
        print("Retry_main is now: ", retry_main)

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


# Handle spotify exceptions
#   - First, it refreshes the Spotify token and retry
#   - If it doesn't work after 3 tries, restart the spotifyd
#   - If it still doesn't work, try calling restart_script()
def handleSpotifyException(e, methodNameStr):
    global retry_DNF, RETRY_MAX

    print("!!@ Handling Spotify Exception..")

    if e.http_status == 404:
        if "Device not found" in str(e):
            print("  !! Device not found in [{}].".format(methodNameStr))
        else:
            print("  !! Spotify 404 error in [{}].".format(methodNameStr))
    if e.http_status == 401:
        print("  !! Spotify Token Expired in [{}]".format(methodNameStr))

    try:
        print("  !! We're on {} out of {} tries.".format(retry_DNF, RETRY_MAX))
        if (retry_DNF < RETRY_MAX):
            print("  !! Case 1: Try refreshing the Spotify Token..")
            refreshSpotifyAuthToken()
        else:
            print("  !! Case 2: Max DeviceNotFound tries reached. Try restarting Spotifyd..")
            # ### restart spotifyd
            subprocess.run(["sudo", "pkill", "spotifyd"]) # Kill existing spotifyd processes
            subprocess.run(["/home/pi/spotifyd", "--config-path", "/home/pi/.config/spotifyd/spotifyd.conf"]) # Restart spotifyd (check if this is the correct path)
            # subprocess.run(["sudo", "systemctl", "restart", "/etc/systemd/user/spotifyd.service"], check=True)
            resetRetryDNF = True

        time.sleep(sleepTimeOnError)
        deviceCheck = compareDeviceID()
        if (deviceCheck):
            print("  !! Device Check Passed!")
            retry_DNF = 0
            return
        else:
            print("  !! Device Check Failed.")
            retry_DNF += 1
            raise

    except:
        print("  !! Case 3: Exception raised. Raise [DNF] and [retry_main] counters.")

        if (retry_DNF > RETRY_MAX):
            restart_script()
            retry_DNF = 0

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
    global sp, serverConnCheck, device_id, clientStates, retry_connection
    global isQPON, isActive, isMusicPlaying, isFadingToBlack
    global prevVolume, currVolume, fadingVolumeFlag

    #Voltage variables
    window_size = 3
    voltage_readings = [0] * window_size  # Initialize with zeros

    if (isVerboseFlagSet(FLAG_PotController)):
        print("  $$ PotController Initialized.")

    while True:
    # Inside your main loop where you read the potentiometer voltage
        try:
            # Read potentiometer voltage
            current_voltage = chan_pot.voltage

            # Update running average readings
            voltage_readings.append(current_voltage)

            # when QP is first turned on, wait a few more readings
            if (len(voltage_readings) < window_size):
                if (isVerboseFlagSet(FLAG_PotController)):
                    print("  $$ Voltage reading is not ready yet.. Size: ", len(voltage_readings))
                continue;
            elif (len(voltage_readings) > window_size):
                voltage_readings.pop(0)  # Remove the oldest reading

            # Calculate a running average
            filtered_voltage = running_average(voltage_readings)
            # filtered_voltage = current_voltage
            if (isVerboseFlagSet(FLAG_PotController)):
                if (currTrackInfo is not None):
                    print("  $$ Filtered voltage: {}, isQPON: {}, isActive: {}, isMusicPlaying:{}, currTracID: {} ({})".format(filtered_voltage, isQPON, isActive, isMusicPlaying, currTrackID, currTrackInfo["name"]))
                else:
                    print("  $$ Filtered voltage: {}, isQPON: {}, isActive: {}, isMusicPlaying:{}, currTrackID: {}".format(filtered_voltage, isQPON, isActive, isMusicPlaying, currTrackID))
               time.sleep(1)

            # The voltage is lower than the 'active' threshold. The client is now 'inactive'.
            #  (1) pause the playback for this client
            #  (2) notify the server
            #  (3) turn the queue lights off
            #  (4) turn the ring light off
            ### if filtered_voltage < 0.03:
            if filtered_voltage < VOLTAGE_THRESHOLD:
                if isQPON:
                    if (isVerboseFlagSet(FLAG_PotController)):
                        print("  $$ Case 1")

                    print("Potentiometer is turned OFF.")
                    # set the flags off so it's not playing the song or detecting any BPM taps
                    isQPON = False
                    isActive = False

                    # forget the track info
                    currTrackID = ''
                    currBPM = -1
                    nextTrackRequested = False
                    startTrackTimestamp = -1

                    # setting the fading flag OFF on inActive
                    fadingVolumeFlag = False

                    # reset tap variables
                    bpmAdded = 0
                    msLastTap = 0
                    tapCount = 0

                    # notify the server that this client is off
                    if (serverConnCheck):
                        setClientInactive()
                        print("Client is set Inactive")

                    # turn the queue and ring lights off

                    if (isVerboseFlagSet(FLAG_FadeOutController)):
                        print("  $$ FadingToBlack flag is set in [potController].")
                    isFadingToBlack = True
                    print("Setting a flag to fade out the lights.")

                elif isActive:
                    # clean up
                    isActive = False

            # The client becomes ON and Active,
            # (1) should start listening to new bpm (set isActive to True)
            # (2) should be connected to the server
            ### elif filtered_voltage > 0.1 and not isQPON:
            # when (filtered_voltage >= VOLTAGE_THRESHOLD)
            else:

                ### V > Vt, but QP is not ON yet
                if (not isQPON):
                    if (isVerboseFlagSet(FLAG_PotController)):
                        print("  $$ Case 2")
                    isQPON = True
                    print("Potentiometer is turned ON.")

                ### V > Vt, and QP is ON
                else:
                    ### QP is ON but not Active --> connect
                    if not isActive:
                        if (isVerboseFlagSet(FLAG_PotController)):
                            print("  $$ Case 2-2")
                            time.sleep(1)

                        while (not serverConnCheck):
                            if (isVerboseFlagSet(FLAG_PotController)):
                                print("Waiting for the server connection..")

                            time.sleep(2)
                        # notify the server that this client is 'active'
                        isActive = True
                        setClientActive()
                        print("Client is now set Active")

                    ### QP is ON and Active --> set volume (play music)
                    else:

                    # # This is when a client is recovered from a disconnection or device not found exception
                    # elif isQPON and serverConnCheck and len(clientStates) == 4 and not clientStates[clientID-1]:
                    #     if (isVerboseFlagSet(FLAG_PotController)):
                    #         print("  $$ Case 3")
                    #
                    #     print("Current client states: ", clientStates)
                    #     # notify the server that this client is 'active'
                    #     isActive = True
                    #     setClientActive()
                    #     print("Client connection is recovered. Request the server to set this client Active")

                    # If a song is being played and the pot value changes, this indicates the volume change.
                    #     *** have this as a seperate thread maybe just to have better code modularity, no point being here anyways
                        # set to a new volume (read the pot) -- prevent sudden volume change
                        currVolume = int(map_to_volume(filtered_voltage))

                        # only update the volume when the new voltage is moved more than a certain threshold
                        if(abs(prevVolume-currVolume) >= 5):
                            if (isVerboseFlagSet(FLAG_PotController)):
                                print("  $$ Case 4 -- Volume Change! {} -> {}".format(prevVolume, currVolume))

                            prevVolume = currVolume

                            with spotify_lock:
                                devices = sp.devices()['devices']
                            if (isVerboseFlagSet(FLAG_PotController)):
                                print("Current devices: ", devices)

                            # pause reading the volume when the volume is fading in or out
                            if (not fadingVolumeFlag):
                                # set to fixed volume as currVolume can be continuously changing
                                print("PotController Changing Volume")
                                with spotify_lock:
                                    sp.volume(prevVolume, device_id)
                            else:
                                if (isVerboseFlagSet(FLAG_PotController)):
                                    print("  $$ Case 5")
                                    print("  $$ Fade flag is set -- setting the volume from the potentiometer is paused.")
                                    time.sleep(1)

        # Restart spotifyd with credentials if device is not found
        except spotipy.exceptions.SpotifyException as e:
            handleSpotifyException(e, "PotController")
            requestQPInfo()

        except requests.exceptions.ConnectTimeout:
            print("  !! Connection timeout in [PotController].")
            print("  !! Retrying after a few seconds..")
            retry_connection += 1
            time.sleep(sleepTimeOnError)
            if (retry_connection >= RETRY_MAX):
                retryServerConnection()

        except requests.exceptions.ReadTimeout:
            print("  !! Read timeout in [PotController].")
            print("  !! Try refreshing Spotify token.")
            refreshSpotifyAuthToken()
            time.sleep(sleepTimeOnError)
            requestQPInfo()

        except Exception as e:
            print(f"  !! An error occurred in [PotController]: {str(e)}")
            time.sleep(sleepTimeOnError)
            requestQPInfo()

# ----------------------------------------------------------

# ----------------------------------------------------------
# Section 2: Client->Server + Client->Spotify Controls

def pushBPMToQueue(bpm):
    global clientID, currCluster

    if (isVerboseFlagSet(FLAG_TapController)):
        print("  $$ Sending a post request to server.")
        print("  $$   bpm: {}, clientID: {}, cluster: {}".format(bpm, clientID, currCluster))

    songToBeQueued=requests.post(baseUrl+"getTrackToQueue", json={"bpm":bpm, "clientID":clientID, "cln":currCluster})

# read the tap once, record the timestamp
# increase or reset the tap count, depending on the interval
def TapBPM():
    global tapCount, msFirstTap, msLastTap, bpmAdded, tapInterval

    msCurr = int(time.time()*1000)
    if(msCurr-msLastTap > 1000*tapInterval):
        if (isVerboseFlagSet(FLAG_TapController)):
            print("  $$ It's been more than {} secs since the last tap. Resetting the tapCount to 0.".format(tapInterval))

        tapCount = 0

    if(tapCount == 0):
        print ("  # First tap. Tapcount: 1")
        msFirstTap = msCurr
        tapCount = 1
    else:
        if msCurr-msFirstTap > 0:
            bpmAvg = 60000 * tapCount / (msCurr - msFirstTap)
            bpmAdded = round(round(bpmAvg * 100) / 100)
        tapCount+=1
        if (isVerboseFlagSet(FLAG_TapController)):
            print ("  $$ Next tap. Tapcount: {}".format(tapCount))

    msLastTap = msCurr

# There is a new BPM that just came in, so notify the server to either play a song or add a song to the queue
def tapController():
    global isActive, bpmAdded, msLastTap, tapCount, tapInterval

    if (isVerboseFlagSet(FLAG_TapController)):
        print("  $$ TapController initialized.")

    while True:
        try:
            msCurr = int(time.time()*1000)

            # the last tap has happened more than x seconds ago -- finish recording
            if msCurr-msLastTap > 1000*tapInterval and bpmAdded > 0:
                print("   # LastTap Detected. Tapcount: {}, bpm: {}".format(tapCount, bpmAdded))
                # notify the server accordingly,
                if isActive:
                    if (isVerboseFlagSet(FLAG_TapController)):
                        print("  $$ Client is active. Notify the server with bpm ", bpmAdded)
                    pushBPMToQueue(bpmAdded)
                else:
                    if (isVerboseFlagSet(FLAG_TapController)):
                        print("  $$ Client is inactive. Discard the bpm input.")

                # reset the variables
                bpmAdded = 0
                msLastTap = 0
                tapCount = 0

            time.sleep(sleepTimeOnError)

        except Exception as e:
            print(f"  !! An unknown error occurred in [tapController]: {str(e)}")
            time.sleep(sleepTimeOnError)
            # reset the variables
            bpmAdded = 0
            msLastTap = 0
            tapCount = 0
            restart_script()

# A worker function to detect and update the tap signals
# This will only run once whenever the tap sensor receives a signal
def tapSensor(channel):
    global isActive

    if GPIO.input(channel):
        if isActive:
            print ("Tap")
            TapBPM()
        else:
            if (isVerboseFlagSet(FLAG_TapController)):
                print("  $$ Inactive Tap.")

# Add event detection for falling edge with debounce time of 50 ms
GPIO.add_event_detect(channel, GPIO.BOTH, bouncetime=50)
# Assign function to GPIO PIN, Run function on change
GPIO.add_event_callback(channel, tapSensor)


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


def fadeInVolume(doFadeOut = False):
    global sp, currVolume, refVolume, device_id, fadingVolumeFlag, retry_connection

    fadingVolumeFlag = True

    ### ---- fade out ---- ###
    if doFadeOut:
        refVolume = currVolume

        while (refVolume > 0):
            refVolume = int(refVolume * 0.5)

            # Ensure volume goes to 0
            if refVolume < 1:
                refVolume = 0

            try:
                with spotify_lock:
                    sp.volume(refVolume, device_id=device_id)

            # Restart spotifyd with credentials if device is not found
            except spotipy.exceptions.SpotifyException as e:
                handleSpotifyException(e, "Fade-Out Volume")
                ## Do not add requestQPInfo() here -- should finish fadeout

            except requests.exceptions.ConnectTimeout:
                print("  !! Connection timeout while [fading out volume].")
                print("  !! Retrying after a few seconds..")
                retry_connection += 1
                time.sleep(sleepTimeOnError)
                if (retry_connection >= RETRY_MAX):
                    retryServerConnection()

                # TODO: check this logic -- see if this still performs fadein/out upon recovery
                print("  *** Quit [Fade-Out] and setting the fadingout flag off.")
                fadingVolumeFlag = False
                requestQPInfo()
                return

            except requests.exceptions.ReadTimeout:
                print("  !! Read timeout while [fading out volume].")
                print("  !! Try refreshing Spotify token.")
                refreshSpotifyAuthToken()
                time.sleep(sleepTimeOnError)
                ## Do not add requestQPInfo() here -- should finish fadeout

            except Exception as e:
                print(f"  !! An unknown error occurred while [fading out volume]: {str(e)}")
                time.sleep(sleepTimeOnError)
                restart_script()
                ## Do not add requestQPInfo() here -- should finish fadeout

            # Delay to prevent hitting API rate limits and to make fade in smoother
            time.sleep(0.2)

    ### ---- fade in ---- ###

    refVolume = 0  # Start from volume 0
    currVolume_copy = currVolume

    while refVolume < currVolume_copy:

        # Increment volume
        refVolume = int(refVolume * 2 + 1)

        # Ensure volume does not exceed target
        if refVolume > currVolume_copy:
            refVolume = currVolume_copy

        try:
            with spotify_lock:
                sp.volume(refVolume, device_id=device_id)

        # Restart spotifyd with credentials if device is not found
        except spotipy.exceptions.SpotifyException as e:
            handleSpotifyException(e, "Fade-In Volume")
            ## Do not add requestQPInfo() here -- should finish fadein

        except requests.exceptions.ConnectTimeout:
            print("  !! Connection timeout while [fading in volume].")
            print("  !! Retrying after a few seconds..")
            retry_connection += 1
            time.sleep(sleepTimeOnError)
            if (retry_connection >= RETRY_MAX):
                retryServerConnection()

            # TODO: check this logic -- see if this still performs fadein/out upon recovery
            print("  *** Quit [Fade-In] and setting the fadingout flag off.")
            fadingVolumeFlag = False
            requestQPInfo()
            return

        except requests.exceptions.ReadTimeout:
            print("  !! Read timeout while [fading in volume].")
            print("  !! Try refreshing Spotify token.")
            refreshSpotifyAuthToken()
            time.sleep(sleepTimeOnError)
            ## Do not add requestQPInfo() here -- should finish fadein

        except Exception as e:
            print(f"  !! An error occurred while [fading in volume]: {str(e)}")
            time.sleep(sleepTimeOnError)
            restart_script()
            ## Do not add requestQPInfo() here -- should finish fadein

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

    if (isVerboseFlagSet(FLAG_QueueLightController)):
        print("  $$ Color Array Builder")
        print("  $$  First pixel: {}".format(pixels[0]))

    for queueLight, queueLightInfo in lightInfo.items():
        colors = queueLightInfo["colors"]
        isNewBPM = queueLightInfo["isNewBPM"]

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
        if (isVerboseFlagSet(FLAG_QueueLightController)):
            print("  $$ Color Arrays are different. Update the queue lights!")
            # print("  $$   Color before: {}".format(colorArrBefore))
            # print("  $$   Color After: {}".format(colorArrAfter))

        # Define the maximum brightness value
        max_brightness = 255
        fade_duration = 0.15 # Adjust the fade duration as desired

        # Calculate the number of steps based on the fade duration and delay
        num_steps = int(fade_duration / 0.01)

        # Fade-out effect
        if not (pixels[0] == [0,0,0,0]):
            if (isVerboseFlagSet(FLAG_QueueLightController)):
                print("  $$ Fading out..")

            for step in range(num_steps, -1, -1):
                brightness = int(step * max_brightness / num_steps)
                for i in range(144):
                    pixels[i] = colorArrBefore[i]
                pixels.brightness = brightness / max_brightness
                pixels.show()
                time.sleep(0.01)

        # Fade-in effect
        if (isVerboseFlagSet(FLAG_QueueLightController)):
            print("  $$ Fading in..")

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
    global lightInfo, updateQueueLight, isActive

    if (isVerboseFlagSet(FLAG_QueueLightController)):
        print("  $$ QueueLightController initialized.")

    while True:
        try:
            if isActive and updateQueueLight:
                    if (isVerboseFlagSet(FLAG_QueueLightController)):
                        print("  $$ Update Queue Light signal received.")

                    colorArrayBuilder(lightInfo)
                    updateQueueLight=False
            elif not isActive and updateQueueLight:
                # if updateQueueLight is on but the QP is inActive, ignore the flag
                updateQueueLight=False
        except Exception as e:
            print(f"  !! An unknown error occurred in [queueLightController]: {str(e)}")
            time.sleep(sleepTimeOnError)
            restart_script()


# the ring light indicates the last client tapped
def ringLightController():
    global lightInfo, pixels, ringLightColor, isActive, isBPMChanged, currBPM, currTrackID

    if (isVerboseFlagSet(FLAG_RingLightController)):
        print("  $$ RingLightController initialized.")

    interval = 0
    beat_interval = 0

    while True:
        # flash the ring light when the QP is active
        if(isActive and currTrackID != ''):

            # calculate the beat interval only once when the bpm changes
            if (isBPMChanged):
                if (isVerboseFlagSet(FLAG_RingLightController)):
                    print("  $$ BPM changed! Re-calculating the interval..")
                    print("  $$ BPM is now: ", currBPM)

                # Calculate the time interval between beats
                interval = 60 / currBPM
                beat_interval = 60 / (currBPM * 2.5)
                isBPMChanged = False

            if (interval > 0 and beat_interval > 0):
                if (isVerboseFlagSet(FLAG_RingLightController)):
                    if (ringLightColor == YELLOW):
                        print("  $$ Current ring light is: YELLOW")
                    elif (ringLightColor == GREEN):
                        print("  $$ Current ring light is: GREEN")
                    elif (ringLightColor == VIOLET):
                        print("  $$ Current ring light is: VIOLET")
                    elif (ringLightColor == ORANGE):
                        print("  $$ Current ring light is: ORANGE")

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


def indicatorLightController():
    global clientID, clientStates

    if (isVerboseFlagSet(FLAG_IndicatorLightController)):
        print("  $$ IndicatorLightController initialized.")

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

        except Exception as e:
            print(f"  !! An unknown error occurred in [indicatorLightController]: {str(e)}")
            time.sleep(sleepTimeOnError)
            restart_script()

def fadeoutController():
    global isFadingToBlack

    if (isVerboseFlagSet(FLAG_FadeOutController)):
        print("  $$ FadeOutController initialized.")

    while True:
        try:
            if(isFadingToBlack):
                print("FadeoutController -- Fading to black..")
                fadeToBlack()
                if (isVerboseFlagSet(FLAG_FadeOutController)):
                    print("  $$ Fade out to black is done. Releasing the flag.")
                isFadingToBlack = False
        except Exception as e:
            print(f"  !! An unknown error occurred in [fadeoutController]: {str(e)}")
            time.sleep(sleepTimeOnError)
            restart_script()

# ----------------------------------------------------------
# Section 5: Music Controls

def ms_to_min_sec_string(milliseconds):
    # Convert milliseconds to seconds
    seconds = milliseconds / 1000
    # Calculate minutes and remaining seconds
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    # Format the result as "{min}:{sec}"
    return f"{minutes:02d}:{remaining_seconds:02d}"

# A wrapper function to save information for cross-checking if the next song coming in is a new song
# This prevents the same song from playing repeatedly
def notifyTrackFinished(trackID):
    global isMusicPlaying, currCluster

    if (isVerboseFlagSet(FLAG_PlaySongController)):
        print("  $$ Pause the music and notify the server.")
        print("  $$ ClientID: {}, (finished)TrackID: {}, cluster: {}".format(clientID, trackID, currCluster))

    isMusicPlaying = False
    res = requests.post(baseUrl+"trackFinished", json={"clientID":clientID, "trackID":trackID, "cln":currCluster})


# A simple function to request the most updated QP Info without modifying anything.
# Need this to recover from any type of disconnection.
def requestQPInfo():
    print("  $$ Requesting the updated QP info from the server.")
    res = requests.post(baseUrl+"requestQPInfo", json={"clientID":clientID})


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
    global sp, device_id, retry_connection
    global currTrackInfo, currTrackID, prevVolume, currVolume, isMusicPlaying, isActive, fadingVolumeFlag, nextTrackRequested
    global startTrackTimestamp, totalTrackTime, elapsedTrackTime, isEarlyTransition

    if (isVerboseFlagSet(FLAG_PlaySongController)):
        print("  $$ PlaySongController is initialized.")

    while True:
        try:
            # QP is INACTIVE
            if not isActive:
                if (isMusicPlaying):
                    if (isVerboseFlagSet(FLAG_PlaySongController)):
                        print("  $$ QP is not active but the music is still playing.")
                        print("  $$ Pause the playback.")

                    isMusicPlaying=False

                    prevVolume = 0
                    currVolume = 0

                    # Add a guard before calling the Apotify API
                    with spotify_lock:
                        devices = sp.devices()['devices']
                        sp.pause_playback(device_id=device_id)

                # even if the music is not playing, clean up the variables
                else:
                    if (isVerboseFlagSet(FLAG_PlaySongController)):
                        print("  $$ QP is now Inactive and NOT playing music.")
                        time.sleep(1)
                    fadingVolumeFlag = False
                    prevVolume = 0
                    currVolume = 0

            # QP is ACTIVE
            else:

                if (startTrackTimestamp > 0 and currTrackID != ''):
                    elapsed_time = (time.time() - startTrackTimestamp) * 1000
                    elapsedTrackTime = int(elapsed_time)

                    if (isVerboseFlagSet(FLAG_PlaySongController)):
                        print(f"Total Track Time: ", ms_to_min_sec_string(totalTrackTime))
                        print(f"Elapsed Track Time: ", ms_to_min_sec_string(elapsedTrackTime))
                        time.sleep(1)

                elif (startTrackTimestamp < 0):
                    if (isVerboseFlagSet(FLAG_PlaySongController)):
                        print("  $$ QP is ON but has no info on when the song started.")
                    time.sleep(1)
                    continue

                elif (currTrackID == ''):
                    if (isVerboseFlagSet(FLAG_PlaySongController)):
                        print("  $$ QP is ON but has no trackID yet.")
                    time.sleep(1)
                    continue
                else:
                    print("  Unknown condition caught in [PlaysongController], ##1. Raise.")
                    raise

                # when the song ends, notify the server and start fading out
                #  ** this condition is not dependant on the music playing, so should be able to handle late recovery
                #  ** this flag should be off when the client receives the server's broadcast message
                if (not nextTrackRequested and elapsedTrackTime > 0 and totalTrackTime > 0 and elapsedTrackTime > totalTrackTime):
                    print("Song has ended")
                    nextTrackRequested = True

                    if (isVerboseFlagSet(FLAG_PlaySongController)):
                        print("  $$ elapsedTrackTime: {}, totalTrackTime: {}".format(elapsedTrackTime, totalTrackTime))

                    notifyTrackFinished(currTrackID)
                    continue

                # if no music is playing, play the music
                if not isMusicPlaying:
                    if (isVerboseFlagSet(FLAG_PlaySongController)):
                        print("  $$ QP is ON but the music is not playing.")

                    if (currTrackID != ""):
                        trackURIs = ["spotify:track:"+currTrackID]

                        elapsed_time = (time.time() - startTrackTimestamp) * 1000
                        elapsedTrackTime = int(elapsed_time)

                        if (isVerboseFlagSet(FLAG_PlaySongController)):
                            formatted_time = ms_to_min_sec_string(elapsedTrackTime)
                            print("  $$ Track [{}] is now at {} in the song.".format(currTrackInfo["name"], formatted_time))
                            print("  $$ Start playback at that time.")

                        # Add a guard before calling the Apotify API
                        with spotify_lock:
                            devices = sp.devices()['devices']
                            sp.start_playback(device_id=device_id, uris=trackURIs, position_ms=elapsedTrackTime)
                            # indicate the song is now playing
                            isMusicPlaying=True

                # if music is playing,
                else:
                    # when the server forces you to skip to the next song,
                    if (isEarlyTransition):
                        elapsed_time = (time.time() - startTrackTimestamp) * 1000
                        elapsedTrackTime = int(elapsed_time)

                        if (isVerboseFlagSet(FLAG_PlaySongController)):
                            print("  $$ Early transition in [PlaySongController]")
                            formatted_time = ms_to_min_sec_string(elapsedTrackTime)
                            print("  $$ The new track [{}] is now at {} in the song.".format(currTrackInfo["name"], formatted_time))
                            print("  $$ Start playback at that time.")

                        trackURIs = ["spotify:track:"+currTrackID]

                        # Add a guard before calling the Apotify API
                        with spotify_lock:
                            devices = sp.devices()['devices']
                            sp.start_playback(device_id=device_id, uris=trackURIs, position_ms=elapsedTrackTime)

                        fadeInVolume(True)
                        isEarlyTransition = False

        except spotipy.exceptions.SpotifyException as e:
            handleSpotifyException(e, "PlaySongController")
            requestQPInfo()

        except requests.exceptions.ConnectTimeout:
            print("  !! Connection timeout in [PlaySongController].")
            print("  !! Retrying after a few seconds..")
            retry_connection += 1
            time.sleep(sleepTimeOnError)
            if (retry_connection >= RETRY_MAX):
                retryServerConnection()

        except requests.exceptions.ReadTimeout:
            print("  !! Read timeout in [PlaySongController].")
            print("  !! Try refreshing Spotify token.")
            refreshSpotifyAuthToken()
            time.sleep(sleepTimeOnError)
            requestQPInfo()

        except Exception as e:
            print(f"  !! An unknown error occurred in [PlaySongController]: {str(e)}")
            time.sleep(sleepTimeOnError)
            restart_script()
            requestQPInfo()


# ----------------------------------------------------------
# Section 6: QueuePlayer Client Main

def on_connect():
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


def on_disconnect():
    global serverConnCheck, isActive, currTrackID, nextTrackRequested, startTrackTimestamp

    serverConnCheck = False
    isActive = False

    # reset the trackID so when the client is recovered, it can resume
    currTrackID = ''
    isMusicPlaying = False
    nextTrackRequested = False
    startTrackTimestamp = -1

    print('Disconnected from server')


def on_state_change(data):
    global clientStates

    print("## State change message received.")
    json_data = json.loads(data) # incoming message is transformed into a JSON object
    print("    Previous client states: ", clientStates)
    clientStates = json_data["activeUsers"]
    print("    Current client states: ", clientStates)


def on_broadcast(data):
    global sp, spToken, clientStates, retry_connection
    global isMusicPlaying, isActive, lightInfo, currTrackInfo, updateQueueLight
    global currBPM, currTrackID, currCluster, ringLightColor, isBPMChanged
    global elapsedTrackTime, totalTrackTime, startTrackTimestamp, isEarlyTransition, nextTrackRequested, currQueuedTrackIDs

    json_data = json.loads(data) # incoming message is transformed into a JSON object
    print("Server Sent the JSON:")
    print(json.dumps(json_data, indent = 2))
    print("    Current client states: ", clientStates)

    if isActive:
        # track changes
        if (json_data["currentTrack"]["trackID"] != currTrackID):
            print("[Broadcast] ## Case 1: New TrackID Received!")

            if (currBPM != json_data["currentTrack"]["bpm"]):
                if (isVerboseFlagSet(FLAG_SocketMessages)):
                    print("  $$ [Broadcast] New BPM! {} -> {}".format(currBPM, json_data["currentTrack"]["bpm"]))

                currBPM = json_data["currentTrack"]["bpm"]
                isBPMChanged = True

            # if the Server's startTrackTimestamp (indicates when the next song should start)
            #    is less (<) than the Client's startTrackTimestamp + the total track time,
            #       (startTrackTimestamp + totalTrackTime)
            # it means there is an early transition to the next song.
            if (json_data["currentTrack"]["startTrackTimestamp"] - startTrackTimestamp > 5 and
                json_data["currentTrack"]["startTrackTimestamp"] < startTrackTimestamp + (totalTrackTime / 1000)):
                if (isVerboseFlagSet(FLAG_SocketMessages)):
                    print("  $$ [Broadcast] Early Transition detected!")
                    print("  $$   (Server) startTrackTimestamp: ", json_data["currentTrack"]["startTrackTimestamp"])
                    print("  $$   (Client) startTrackTimestamp: ", startTrackTimestamp)
                    print("  $$   totalTrackTime: {} ({})".format(totalTrackTime, ms_to_min_sec_string(totalTrackTime)))
                    print("  $$    --> {} (Server's STTS) <? {} (Client's STTS + totalTrackTime) : ".format(json_data["currentTrack"]["startTrackTimestamp"], startTrackTimestamp + (totalTrackTime/1000)))

                isEarlyTransition = True
            else:
                isEarlyTransition = False

            currTrackID = json_data["currentTrack"]["trackID"]
            currCluster = json_data["currentTrack"]["cluster_number"]

            startTrackTimestamp = json_data["currentTrack"]["startTrackTimestamp"]

            if (isVerboseFlagSet(FLAG_SocketMessages)):
                print("  $$ [Broadcast] Update Track Info: ")
                print("  $$   startTrackTimestamp: ", startTrackTimestamp)
                print("  $$   TrackID: ", currTrackID)
                print("  $$   Cluster: ", currCluster)

            lightInfo = json_data["lightInfo"]

            if (isVerboseFlagSet(FLAG_QueueLightController)):
                print("  $$ [Broadcast - Case 1] Setting the queueLight flag.")
            updateQueueLight = True

            # change the ring light only when the current track is added by tapping (by anyone)
            #    or the ring color is actually different -- this is for the clients who joins the queue
            #
            if (lightInfo["queueLight1"]["isNewBPM"] or ringLightColor != lightInfo["queueLight1"]["ringLight"]):
                ringLightColor = lightInfo["queueLight1"]["ringLight"]

                if (isVerboseFlagSet(FLAG_RingLightController)):
                    print("  $$ [Broadcast] RingLightColor updated!")
                    print("  $$   Ring light is now: ", ringLightColor)

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

            newTrackInfo = None
            while (newTrackInfo is None):
                try:
                    with spotify_lock:
                        newTrackInfo = sp.track(currTrackID)

                except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout):
                    print("  !! Connection or Read timeout while requesting track info.")
                    print("  !! Retrying after a few seconds..")
                    retry_connection += 1
                    time.sleep(sleepTimeOnError)

                    if (retry_connection >= RETRY_MAX):
                        refreshSpotifyAuthToken()
                        retryServerConnection()

                    requestQPInfo()

                #Last Resort is to restart script
                # except requests.exceptions.ReadTimeout:
                    # print("Minor Setback. Restarting the script...")
                    # restart_script()

                # Restart spotifyd with credentials if device is not found
                except spotipy.exceptions.SpotifyException as e:
                    handleSpotifyException(e, "Broadcast")
                    requestQPInfo()

                except Exception as e:
                    print(f"  !! An error occurred in [broadcast]: {str(e)}")
                    time.sleep(sleepTimeOnError)
                    restart_script()
                    requestQPInfo()

            currTrackInfo = newTrackInfo
            totalTrackTime = newTrackInfo['duration_ms']

            if (isVerboseFlagSet(FLAG_SocketMessages)):
                print("  $$ [Broadcast] New Track Info: ")
                # print(currTrackInfo)

            nextTrackRequested = False

        # When the queue changes, leave the track info and update the light info only
        elif (json_data["queuedTrackIDs"] != currQueuedTrackIDs):
            print("[Broadcast] ## Case 2: Same Track in play, but the Queue is updated.")

            currQueuedTrackIDs = json_data["queuedTrackIDs"]
            lightInfo = json_data["lightInfo"]
            if (isVerboseFlagSet(FLAG_QueueLightController)):
                print("  $$ [Broadcast - Case 2] Setting the queueLight flag.")
            updateQueueLight = True
            # # may need this here
            # nextTrackRequested = False

        else:
            print("[Broadcast] ## Case 3: Same Track in play. I'm already on this track.")

            # ### TODO: may not need this if the potentiometer reading works well on recovery.
            # currQueuedTrackIDs = json_data["queuedTrackIDs"]
            # lightInfo = json_data["lightInfo"]
            # if (isVerboseFlagSet(FLAG_QueueLightController)):
            #     print("  $$ [Broadcast - Case 3] Setting the queueLight flag.")
            # updateQueueLight = True
    else:
        print("[Broadcast] ## Case 4: Received JSON but I'm currently inactive.")

    print("///////////////////////////////////////////////////////////////////////////////////////////////////////////")


def main():
    global retry_main

    retry_main = 0

    print("[Main] Start of script.")

    thread_TapSensor = None
    thread_PlaySong = None
    thread_Potentiometer = None
    thread_TapController = None
    thread_QueueLight = None
    thread_RingLight = None
    thread_IndicatorLight = None
    thread_Fadeout = None

    while (retry_connection < RETRY_MAX):
        try:
            # TapSensor
            if (thread_TapSensor is None):
                thread_TapSensor = threading.Thread(target=tapSensor(channel))
            if not thread_TapSensor.is_alive():
                thread_TapSensor.start()

            # PlaySong
            if (thread_PlaySong is None):
                thread_PlaySong = threading.Thread(target=playSongController)
            if not thread_PlaySong.is_alive():
                thread_PlaySong.start()

            # Potentiometer
            if (thread_Potentiometer is None):
                thread_Potentiometer = threading.Thread(target=potController)
            if not thread_Potentiometer.is_alive():
                thread_Potentiometer.start()

            # TapController
            if (thread_TapController is None):
                thread_TapController = threading.Thread(target=tapController)
            if not thread_TapController.is_alive():
                thread_TapController.start()

            # Queue Light
            if (thread_QueueLight is None):
                thread_QueueLight = threading.Thread(target=queueLightController)
            if not thread_QueueLight.is_alive():
                thread_QueueLight.start()

            # Ring Light
            if (thread_RingLight is None):
                thread_RingLight = threading.Thread(target=ringLightController)
            if not thread_RingLight.is_alive():
                thread_RingLight.start()

            # Indicator Light
            if (thread_IndicatorLight is None):
                thread_IndicatorLight = threading.Thread(target=indicatorLightController)
            if not thread_IndicatorLight.is_alive():
                thread_IndicatorLight.start()

            # Fade-out to Black
            if (thread_Fadeout is None):
                thread_Fadeout = threading.Thread(target=fadeoutController)
            if not thread_Fadeout.is_alive():
                thread_Fadeout.start()

            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()
            print("[Main] Socket connection established.")
            sio.wait()

        except Exception as e:
            print(f"  !! An unknown error occurred in [QueuePlayerMain]: {str(e)}")
            restart_script()
            time.sleep(sleepTimeOnError)
            requestQPInfo()

    # If max retries exceeded, restart the script
    print("Maximum retry count exceeded in [Main]. Attempt to restarting the script.")
    restart_script()
    # ----------------------------------------------------------

# Check if the script is being run directly
if __name__ == "__main__":
    sio = socketio.Client()
    print("trying to connect")

    # Register socket event functions with socket client
    sio.on("connect", on_connect)
    sio.on("disconnect", on_disconnect)
    sio.on("stateChange", on_state_change)
    sio.on("broadcast", on_broadcast)

    main()
