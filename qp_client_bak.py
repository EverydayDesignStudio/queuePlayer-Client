
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
bpmCountCheck=False      # a flag to indicate if the client is ready to read new BPMs
playingCheck=False       # whether a song is currently being played
seekCheck=False          # whether this client is trying to join the existing queue, looking for the timestamp/duration
# newCheck=False         
durationCheck=True       # a flag to indicate if the exact duration needs to be figured out for the current song
lightCheck = False       # is the light for the queue on?
lights = None
readyStateCheck = False       # Upon "Initial", is the client waiting for a user to tap?
ringLightCheck = False   # is the light for the ring on? -- the ring light indicates the last person who tapped
fadeToBlackCheck = False # lights for the queue and the ring will go out when the power is off
serverConnCheck = False  # check the server connection
cluster = None           # the current song's cluster in the DB 

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
prevVolumeVal = 0              # previous value for volume
currVolumeValumeVal = 100            # current value for volume

# Lights function variables
colorArrBefore=[(0,0,0,0)]*144    # indicates four queue colors for the 'current' state
colorArrAfter=[0]*144             # indicates four queue colors for the 'next' state

# Global idling fail-safe variable
prevtrackID=''
prevDuration=0
currtrackID=''
currDuration=None

# Local timer variables for song end check
startTime=None
totalTime=None
seekedClient=0                    # local elapsed time to seek for the song duration >> looking for the exact time in song

# Global seek variable
seekedPlayer=0                    # global(server's) timestamp for the song duration >> reference time of the current song on the server

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
        else:
            raise
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
    global sp, bpmCountCheck, prevVolumeVal, currVolumeVal, playingCheck, currtrackID, seekedClient, durationCheck, serverConnCheck, fadeToBlackCheck, device_id, clientStates
    
    #Voltage variables
    window_size = 4
    voltage_readings = [0] * window_size  # Initialize with zeros
    
    try:
    # Inside your main loop where you read the potentiometer voltage
        while True:
            # Read potentiometer voltage
            current_voltage = chan_pot.voltage

            # Update moving average readings
            voltage_readings.append(current_voltage)
            if len(voltage_readings) > window_size:
                voltage_readings.pop(0)  # Remove the oldest reading

            # Calculate the moving average
            filtered_voltage = moving_average(voltage_readings)
            filtered_voltage = current_voltage
            #print(filtered_voltage)

            # The voltage is lower than the 'active' threshold. The client is now 'inactive'.
            #  (1) pause the playback for this client
            #  (2) notify the server
            #  (3) turn the queue lights off
            #  (4) turn the ring light off
            if filtered_voltage < 0.03:
                # double-check if the song is being played and the BPM is 'tappable'
                if playingCheck and bpmCountCheck:
                    # set the flags off so it's not playing the song or detecting any BPM taps
                    playingCheck=False
                    bpmCountCheck=False

                    # request to pause the song 
                    try:
                        sp.pause_playback(device_id=device_id)
                    # will give the error for spotify command failed have to incorporate similar mechanism as volume
                    except spotipy.exceptions.SpotifyException as e:
                        # Check for "device not found" error
                        if e.http_status == 404 and "Device not found" in str(e):
                            print("Device not found. [in PotController when turning the pot off] Restarting spotifyd...")
                            
                            restart_spotifyd()
                            
                            print("Disconnecting from server...")
                            sio.disconnect()
                            time.sleep(2)
                            print("Reconnecting to server...")
                            #sio.connect('https://qp-master-server.herokuapp.com/')
                            socketConnection()
                        elif e.http_status == 401:
                            print("Spotify Token Expired in potController when turning the pot off")
                            refreshSpotifyAuthToken()
                        else:
                            raise
                    
                    # notify the server that this client is off
                    setClientInactive()
                    print("Potentiometer is turned OFF.")
                    print("Client is set Inactive")

                    # TODO: ???
                    seekData=requests.post(baseUrl+"updateSeek", json={"seek":seekedClient+seekedPlayer, "song":currtrackID,"prompt":"Continue"})                
                    
                    # turn the queue and ring lights off
                    fadeToBlackCheck = True
                

            # The client becomes 'active',
            # (1) should start listening to new bpm (set BPMCountCheck to True)
            # (2) should be connected to the server
            elif filtered_voltage > 0.1 and not bpmCountCheck and serverConnCheck:
                # set to a new volume (read the pot)
                currVolumeVal = int (map_to_volume(chan_pot.voltage)) #set current volume to potentiometer value
                #currVolumeVal = int(map_to_volume(filtered_voltage))
                
                bpmCountCheck=True
                
                # notify the server that this client is 'active'
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
            if bpmCountCheck and playingCheck:
                currVolumeVal = int(map_to_volume(chan_pot.voltage)) 
                #currVolumeVal = int(map_to_volume(filtered_voltage))
                #print(currVolumeVal)

                # only update the volume when the new voltage is moved more than a certain threshold
                if(abs(prevVolumeVal-currVolumeVal) >= 5):
                    try:
                        devices = sp.devices()['devices']
                        print("potController Changing Volume")
                        print("Current devices: ", devices)
                        sp.volume(currVolumeVal, device_id)
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
                        else:
                            raise

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
                        
                    prevVolumeVal = currVolumeVal
                    print("changing volume")

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

def pushBPMToPlay(bpmAdded):
    songToBePlayed=requests.post(baseUrl+"getTrackToPlay", json={"bpm":bpmAdded, "clientID":clientID})

def pushBPMToQueue(bpmAdded):
    songToBeQueued=requests.post(baseUrl+"getTrackToQueue", json={"bpm":bpmAdded, "clientID":clientID, "cln":cluster})

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
    bpmTapCheck=True

# There is a new BPM that just came in, so notify the server to either play a song or add a song to the queue
def tapController():    
    global playingCheck, bpmAdded, msLastTap, tapCount, tapInterval, readyStateCheck

    while True:
            
        msCurr = int(time.time()*1000)

        try:
            # the last tap has happened more than 2 seconds ago -- finish recording
            if msCurr-msLastTap > 1000*tapInterval and bpmAdded > 0:
                print("   # LastTap Detected. BPM: {}".format(bpmAdded))
                #readyStateCheck = False
                # notify the server accordingly,
                if playingCheck:
                    pushBPMToQueue(bpmAdded)
                else:
                    pushBPMToPlay(bpmAdded)
                
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
    global bpmCountCheck, bpmTimer
        
    if bpmCountCheck:
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


# play a song with a certain timestamp
# only called by when the server sends the message when,
#  (1) the client is just turned 'active' and acknowledged by the server
#  (2) the song is finished and the server broadcasts (is done seeking) the next song to play
def playSong(trkArr, pos):
    global sp, playingCheck, durationCheck
    
    try:
        devices = sp.devices()['devices']
        print("PlaySong.")
        print("Current devices: ", devices)
        sp.start_playback(device_id=device_id, uris=trkArr, position_ms=pos) 
        sp.volume(currVolumeVal, device_id)
    
    except requests.exceptions.ConnectTimeout:
        print("Connection timeout while playing a song")
        print("Disconnecting from server...")
        sio.disconnect()
        time.sleep(2)
        print("Reconnecting to server...")
        #sio.connect('https://qp-master-server.herokuapp.com/')
        socketConnection()
        
    except requests.exceptions.ReadTimeout:
        print("Read timeout while playing a song")

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
            print("Device not found. [in PlaySong] Restarting spotifyd...")
            
            restart_spotifyd()
        
            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()
        elif e.http_status == 401:
            print("Spotify Token Expired in playsong method")
            refreshSpotifyAuthToken()
        else:
            raise
    
    # indicate the song is now playing
    playingCheck=True
    # TODO: why is this set to True here?
    durationCheck=True
        
# A wrapper function to save information for cross-checking if the next song coming in is a new song 
# This prevents the same song from playing repeatedly
def playSongsToContinue(songDuration, trackID, msg): 
    global playingCheck, prevDuration, prevtrackID, cluster
    playingCheck=False
    prevDuration=songDuration
    prevtrackID=trackID
    continueSong=requests.get(baseUrl+"continuePlaying", json={"clientID":clientID, "msg":msg, "cln":cluster})

# def tapController():
    # while True:
        # try:
            # if bpmCountCheck:
                # value = input()
                # if(value==""):
                    # TapBPM()
        # except KeyboardInterrupt:
            # print("Interrupted by Keyboard, script terminated")

            # sio.disconnect()
            # time.sleep(2)
            # sio.connect('https://qp-master-server.herokuapp.com/')

    
    # print("inside inifiniteloop1")
    # debounce_time = 0.05
    # current_time = time.time()

    # try:
        # #if bpmCountCheck:
        # if (current_time - tapController.last_time) > debounce_time:
            # if GPIO.input(channel):
                # TapBPM()
                # print("Tap")
            # tapController.last_time = current_time
    # except KeyboardInterrupt:
        # print("Interrupted by Keyboard, script terminated")

        # sio.disconnect()
        # time.sleep(2)
        # sio.connect('https://qp-master-server.herokuapp.com/')
       
# tapController.last_time = time.time()

    # if GPIO.input(channel):
            # TapBPM()
            # print ("Tap")


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

# ----------------------------------------------------------
# Section 3: NeoPixel & Ring Light Control

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


def colorArrayBuilder(lights):
    global colorArrBefore, colorArrAfter, pixels
    n = 0
    print("inside colorArrayBuilder")
    print(pixels[0])

    for queueLight in lights:
        print("for loop enters")
        colors = lights[queueLight]["colors"]
        isNewBPM = lights[queueLight]["isNewBPM"]
        
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


def ringLightUpdate(ringColor, bpm):
    global playingCheck, pixels

    interval = 60 / bpm  # Calculate the time interval between beats
    beat_interval = 60 / (bpm * 2.5)
    
    while playingCheck:

        # ring lights on
        for i in range(144, 160):
            pixels[i] = ringColor
        pixels.show()
        time.sleep(beat_interval)

        # ring lights off
        for i in range(144, 160):
            pixels[i] = (0, 0, 0, 0)
        pixels.show()
        time.sleep(beat_interval)
        

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
    
#Called when server restarts to prompt user to tap a BPM
def readyState(): #Should be color values in masterSever script
    global clientColor, pixels, num_pixels
    
    # max_brightness = 255
    # fade_duration = 0.25 #2 seconds
    # fade_steps = 100

    # fade_interval = fade_duration/fade_steps #smoothly fade brightness up/down 100 steps in 2 seconds

    # while True:
        # #Fade in 
        # for brightness in range(fade_steps, 255, 5):
            # for i in range (num_pixels):
                # color_rs_fi = (0,0,0,0)
                # for j in range (4):
                    # color_rs_fi[j] = clientColor[j] * brightness/fade_steps
                    # if (color_rs_fi[j] > 255):
                        # print("   color_rs_fi [", i, ",", j, "] > 255")
                # pixels[i] = color_rs_fi
                # # pixels[i] = tuple(int(clientColor[j] * brightness/fade_steps) for j in range(4)) #4 = RGBW pixels
            # pixels.show()
            # time.sleep(fade_interval)

        # #Fade out 
        # for brightness in range(fade_steps, 0, -5): #fade brightness down to -1, by 1 each iteration
            # for i in range (num_pixels):
                # color_rs_fo = (0,0,0,0)
                # for j in range (4):
                    # color_rs_fo[j] = clientColor[j] * brightness/fade_steps
                    # if (color_rs_fo[j] < 0):
                        # print("   color_rs_fo [", i, ",", j, "] < 0")
                # pixels[i] = color_rs_fo
                # #pixels[i] = tuple(int(clientColor[j] * brightness/fade_steps) for j in range(4))
            # pixels.show()
            # time.sleep(fade_interval)
            
    fade_duration = 2 #2 seconds
    fade_steps = 30

    fade_interval = fade_duration/fade_steps #smoothly fade brightness up/down 100 steps in 2 seconds

    while True:
        #Fade in 
        for brightness in range(fade_steps):
            for i in range (num_pixels):
                pixels[i] = tuple(max(0, min(255, int(clientColor[j] * brightness/fade_steps))) for j in range(4)) #4 = RGBW pixels
            pixels.show()
            time.sleep(fade_interval)

        #Fade out 
        for brightness in range(fade_steps, -1, -3): #fade brightness down to -1, by 1 each iteration
            for i in range (num_pixels):
                pixels[i] = tuple(max(0, min(255, int(clientColor[j] * brightness/fade_steps))) for j in range(4))
            pixels.show()
            time.sleep(fade_interval)
        
# ----------------------------------------------------------
# Section 4: Timer Controls     

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
#      Then, request the server for the next song —> continuePlaying
def playSongController():
    global sp, prevDuration, prevtrackID, startTime, totalTime, durationCheck, currtrackID, seekCheck, seekedPlayer, seekedClient, currDuration, playback, currVolumeVal

    try:
        while True:
            # if a song is being played,
            if playingCheck: 
                # and if the song duration needs to be figured out,
                if(durationCheck):
                    print("Duration Checking")
                    try:
                        # request the current song's info and find the exact duration
                        currSongItem = sp.currently_playing()['item']
                    except spotipy.exceptions.SpotifyException as e:
                        # Check for "device not found" error
                        if e.http_status == 404 and "Device not found" in str(e):
                            print("Device not found. [in PlaySongController when loading the currently playing song] Restarting spotifyd...")
                            
                            restart_spotifyd()
                            
                            print("Disconnecting from server...")
                            sio.disconnect()
                            time.sleep(2)
                            print("Reconnecting to server...")
                            #sio.connect('https://qp-master-server.herokuapp.com/')
                            socketConnection()
                        elif e.http_status == 401:
                            print("Spotify Token Expired in PlaySongController when loading the current song")
                            refreshSpotifyAuthToken()
                        else:
                            raise
                    except requests.exceptions.ReadTimeout:
                        print("Read timeout while checking for currently playing song")
                        print("Disconnecting from server...")
                        sio.disconnect()
                        time.sleep(2)

                        refreshSpotifyAuthToken()
                        
                        print("Reconnecting to server...")
                        #sio.connect('https://qp-master-server.herokuapp.com/')
                        socketConnection()

                    if(currSongItem):
                        durationCheck=False
                        print("Duration is set")
                        currDuration=currSongItem['duration_ms']
                        currtrackID=currSongItem['id']

                        # if the client is joining the others, calculate the duration in respect to the 'seekedPlayer' timestamp
                        if(seekCheck):
                            print("Duration set by seeking")
                            totalTime=currSongItem['duration_ms']-seekedPlayer
                            seekCheck=False
                        else:
                            totalTime=currDuration
                        startTime=time.time()

                if(not durationCheck):
                    elapsed_time=(time.time() - startTime) * 1000 
                    seekedClient=int(elapsed_time)
                    if prevDuration==currDuration or prevtrackID==currtrackID:
                            print("Forcing to Continue")
                            print("prevtrackID", prevtrackID)
                            print("currID",currtrackID)
                            playSongsToContinue(currDuration, currtrackID, "Immediate")

                    # if the total time in the song is within the last 10s of the song,
                    # prepare to move on to the next song
                    if totalTime-seekedClient<=10000:
                        print("Fading out")
                        try:
                            playback = sp.current_playback()
                            
                            if playback != None and playback['device'] != None:
                                currVolumeVal = playback['device']['volume_percent']
                                # volume fades out
                                currVolumeVal=currVolumeVal*0.95
                                sp.volume(int(currVolumeVal), device_id)  
                                
                        except spotipy.exceptions.SpotifyException as e:
                            # Check for "device not found" error
                            if e.http_status == 404 and "Device not found" in str(e):
                                print("Device not found. [in PlaySongController when getting the current playback] Restarting spotifyd...")
                                
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
                            else:
                                raise 
                            
                        except requests.exceptions.ReadTimeout:
                            print("Read timeout while checking for current playback state")
                            print("Disconnecting from server...")
                            sio.disconnect()
                            time.sleep(2)

                            refreshSpotifyAuthToken()
                            
                            print("Reconnecting to server...")
                            #sio.connect('https://qp-master-server.herokuapp.com/')
                            socketConnection()
                    
                    # if the song reaches the end (within the last 2s), end the song
                    if totalTime-elapsed_time<=2000:
                        print("Song has ended")
                        seekedPlayer=0
                        playSongsToContinue(currDuration,currtrackID, "Normal")          
            else:
                rx=1
    except KeyboardInterrupt:
        print("Interrupted by Keyboard, script terminated")

        sio.disconnect()

        time.sleep(2)
        #sio.connect('https://qp-master-server.herokuapp.com/')
        socketConnection()
        
    except TimeoutError:
        print("Timeout Error in playSongController")
        
        print("Disconnecting from server...")
        sio.disconnect()
        time.sleep(2)
        print("Reconnecting to server...")
        #sio.connect('https://qp-master-server.herokuapp.com/')
        socketConnection()
# ----------------------------------------------------------

def moving_average(values):
    return sum(values) / len(values)
    
    

def queueLightController():
    global lights,lightCheck, readyStateCheck
    
    try:
        while True:
            if (lightCheck):
            #if(lightCheck and not readyStateCheck):
                #print("color should be updating")
                colorArrayBuilder(lights)
                #showNewBPM(lights)
                lightCheck=False
    except TimeoutError:
        print("Timeout Error in queueLightController")

        print("Disconnecting from server...")
        sio.disconnect()
        time.sleep(2)
        print("Reconnecting to server...")
        #sio.connect('https://qp-master-server.herokuapp.com/')
        socketConnection()

def ringLightController():
    global lights, ringLightCheck, playingCheck, readyStateCheck
    
    try:
        while True:
            #if(ringLightCheck and playingCheck and not readyStateCheck):
            if(ringLightCheck and playingCheck):
                print("inside ringLightController if block")
                ringLightUpdate(lights["queueLight1"]["ringLight"], lights["queueLight1"]["bpm"])
                ringLightCheck=False
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
    
    try:
        while True:

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
    global fadeToBlackCheck
    
    try:
        while True:
            if(fadeToBlackCheck):
                print("fading to black")
                fadeToBlack()
                fadeToBlackCheck = False
    except TimeoutError:
        print("Timeout Error in fadeoutController")

        print("Disconnecting from server...")
        sio.disconnect()
        time.sleep(2)
        print("Reconnecting to server...")
        #sio.connect('https://qp-master-server.herokuapp.com/')
        socketConnection()


# def readyStateController():
    # global readyStateCheck, bpmCountCheck, serverConnCheck
    
    # try:
        # while True:
            # if(readyStateCheck and bpmCountCheck and serverConnCheck):
                # #print("inside readyStateController")
    
                # print("readyState: ", readyStateCheck)
                # #readyState()
    # except TimeoutError:
        # print("Timeout Error in ringLightController")

        # print("Disconnecting from server...")
        # sio.disconnect()
        # time.sleep(2)
        # print("Reconnecting to server...")
        # #sio.connect('https://qp-master-server.herokuapp.com/')
        # socketConnection()


try:
    
    print("start of script")
    thread_TapSensor = threading.Thread(target=tapSensor(channel))
    thread_TapSensor.start()
    
    # thread1 = threading.Thread(target=tapController)
    # thread1.start()

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

    # thread_readyState = threading.Thread(target=readyStateController)
    # thread_readyState.start()


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
        sio.emit('connect_user',{"clientID":clientID})

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
        global serverConnCheck, bpmCountCheck
        
        serverConnCheck = False
        bpmCountCheck = False
        print('Disconnected from server')

    @sio.event
    def message(data):
        global playingCheck, seekCheck, lightCheck, ringLightCheck, bpmCountCheck, readyStateCheck
        global sp, spToken, currtrackID, seekedPlayer, lights, clientStates, cluster, bpmAdded

        json_data = json.loads(data) # incoming message is transformed into a JSON object
        print("Server Sent the JSON:")
        print(json.dumps(json_data, indent = 2))

        if(json_data["msg"] == "Initial"):
            print("Initial!")
            #readyStateCheck = True
        else:
            clientStates = json_data["activeUsers"]
        
        print("json_data_activeUsers: ", json_data["activeUsers"][clientID-1])
        print("json_data_msg: ", json_data["msg"])
        if(json_data["activeUsers"][clientID-1]==True):
            if(json_data["msg"]=="Active" or json_data["msg"]=="Queue" or json_data["msg"]=="Song" or json_data["msg"]=="Backup"):
                
                print("Message is not initial")
                #readyStateCheck = False
                #colorArrayBuilder(json_data["lights"])
                lights=json_data["lights"]
                lightCheck=True
                # trying to turn the right light ON when 'active' will make the client hangs, waiting for any song to be played
                if (json_data["msg"]!="Active"):
                    ringLightCheck = True
                clientStates = json_data["activeUsers"]
                cluster = json_data["songdata"]["cluster_number"]

                print("bpmCountCheck", bpmCountCheck)
                if(json_data["msg"]=="Song" and bpmCountCheck):
                    print("playing song")
                    try:
                        playSong(["spotify:track:"+json_data["songdata"]["trackID"]],json_data["songdata"]["timestamp"])
                    except Exception as e:
                        print(f"An error occurred in the message thread: {str(e)}")

            elif(json_data["msg"]=="Seeking"):
                if playingCheck:
                    print("Updating seek")
                    try:
                        currSeeker=sp.currently_playing()
                        
                    ### I would keep this exception block here because it's making a direct call to the Spotify object,
                    ### and if there's device not found error, there is no way to recover/restart.
                    except spotipy.exceptions.SpotifyException as e:
                        # Check for "device not found" error
                        if e.http_status == 404 and "Device not found" in str(e):
                            print("Device not found. [in 'Seeking' callback] Restarting spotifyd...")

                            restart_spotifyd()

                            print("Disconnecting from server...")
                            sio.disconnect()
                            time.sleep(2)
                            print("Reconnecting to server...")
                            #sio.connect('https://qp-master-server.herokuapp.com/')
                            socketConnection()
                        elif e.http_status == 401:
                            print("Spotify Token Expired in 'Seeking' callback")
                            refreshSpotifyAuthToken()
                        else:
                            raise
                    except requests.exceptions.ReadTimeout:
                        print("!! Read Timeout")
                        print("Disconnecting from server...")
                        sio.disconnect()
                        time.sleep(2)

                        refreshSpotifyAuthToken()
                        
                        print("Reconnecting to server...")
                        #sio.connect('https://qp-master-server.herokuapp.com/')
                        socketConnection()
                        
                    seekData=requests.post(baseUrl+"updateSeek", json={"seek":currSeeker['progress_ms'], "song":currSeeker['item']['id'],"prompt":"Bro"})
            
            elif(json_data["msg"]=="SeekSong"):
                if not playingCheck and bpmCountCheck:
                    cluster = json_data["songdata"]["cluster_number"]
                    print("This is the new client")
                    seekCheck=True
                    clientStates = json_data["activeUsers"]
                    seekedPlayer=json_data["songdata"]["timestamp"]
                    print("json retrieved")
                    playSong(["spotify:track:"+json_data["songdata"]["trackID"]],json_data["songdata"]["timestamp"])
                    print("playsong")

                    lights=json_data["lights"]
                    lightCheck=True
                    ringLightCheck = True
        
        print("///////////////////////////////////////////////////////////////////////////////////////////////////////////")

    print("should be connected")
    #sio.connect('https://qp-master-server.herokuapp.com/')
    socketConnection()
    sio.wait()
except KeyboardInterrupt:
    print("Interrupted by Keyboard, script terminated")
    
    print("Disconnecting from server...")
    sio.disconnect()
    # playingCheck=False
    # bpmCountCheck=False
    time.sleep(2)
    print("Reconnecting to server...")
    socketConnection()
    #sio.connect('https://qp-master-server.herokuapp.com/')

# ----------------------------------------------------------
