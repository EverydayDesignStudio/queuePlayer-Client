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
import spotipy
import subprocess
from spotipy.oauth2 import SpotifyOAuth
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
pixels = neopixel.NeoPixel(pixel_pin1, num_pixels, brightness=10, auto_write=False, pixel_order=ORDER)
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

clientID=2
device_id=None
sp=None

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
# rotation = None
# rotationCheck = False    
ringLightCheck = False   # is the light for the ring on? -- the ring light indicates the last person who tapped
fadeToBlackCheck = False # lights for the queue and the ring will go out when the power is off
serverConnCheck = False  # check the server connection
cluster = None           # the current song's cluster in the DB 

clientStates = []        # shows the status of all four clients (e.g., [True, True, False, False])

# BPM function variables
bpmAdded=215             # default base BPM to start with
tapCount=0               # the number of taps detected
tapInterval=3            # if no more tap is detected within 3 seconds, stop recording and calculate a new BPM
msFirstTap=0             # timestamp of the first detected tap
msLastTap=0              # timestamp of the last entered tap

# Server Variable
baseUrl="https://qp-master-server.herokuapp.com/"

# Global volume variables 
prevVal = 0              # previous value for volume
currVol = 100            # current value for volume

# Lights function variables
colorArrBefore=[(0,0,0,0)]*144    # indicates four queue colors for the 'current' state
colorArrAfter=[0]*144             # indicates four queue colors for the 'next' state

# Global idling fail-safe variable
prevID=''
prevDuration=0
currSongID=''
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
            
            
# Function to restart spotifyd -- checking the device connection
def restart_spotifyd():
    device_is_found = False
    while not device_is_found:
        try:
            print("Device not found. Reconnecting to Spotify...")
            subprocess.run(["sudo", "pkill", "spotifyd"]) # Kill existing spotifyd processes
            subprocess.run(["/home/pi/spotifyd", "--no-daemon", "--config-path", "/home/pi/.config/spotifyd/spotifyd.conf"]) # Restart spotifyd (check if this is the correct path)
            device_is_found = True
        except Exception as e:
            print(f"An error occurred while restarting Spotifyd: {str(e)}")
            time.sleep(2)

def restart_script():
    # Add any cleanup or state reset logic here
    time.sleep(5)  # Optional delay before restarting to avoid immediate restart loop
    print("Restarting the script...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

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
    global bpmCountCheck, prevVal, currVol, playingCheck, currSongID, seekedClient, durationCheck, fadeToBlackCheck
    
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
                    sp.pause_playback(device_id=device_id) # will give the error for spotify command failed have to incorporate similar mechanism as volume
                    
                    # notify the server that this client is off
                    setClientInactive()
                    print("Client is set Inactive")

                    # TODO: ???
                    seekData=requests.post(baseUrl+"updateSeek", json={"seek":seekedClient+seekedPlayer, "song":currSongID,"prompt":"Continue"})                
                    
                    # turn the queue and ring lights off
                    fadeToBlackCheck = True
                

            # The client becomes 'active',
            # (1) should start listening to new bpm (set BPMCountCheck to True)
            # (2) should be connected to the server
            elif filtered_voltage > 0.1 and not bpmCountCheck and serverConnCheck:
                # set to a new volume (read the pot)
                currVol = int (map_to_volume(chan_pot.voltage)) #set current volume to potentiometer value
                #currVol = int(map_to_volume(filtered_voltage))
                
                bpmCountCheck=True
                
                # notify the server that this client is 'active'
                setClientActive()
                print("Client is set Active")

            # If a song is being played and the pot value changes, this indicates the volume change.
            #     *** have this as a seperate thread maybe just to have better code modularity, no point being here anyways
            if bpmCountCheck and playingCheck:
                currVol = int(map_to_volume(chan_pot.voltage)) 
                #currVol = int(map_to_volume(filtered_voltage))
                #print(currVol)

                # only update the volume when the new voltage is moved more than a certain threshold
                if(abs(prevVal-currVol) >= 5):
                    try:
                        sp.volume(currVol, device_id)
                    except:
                        print("Timeout while changing volume")
                        print("Disconnecting from server...")
                        sio.disconnect()
                        time.sleep(2)
                        print("Reconnecting to server...")
                        #sio.connect('https://qp-master-server.herokuapp.com/')
                        socketConnection()
                        
                    prevVal = currVol
                    print("changing volume")

    # this is only for testing
    except KeyboardInterrupt:
        print("Interrupted by Keyboard, script terminated")

        sio.disconnect()
        time.sleep(2)
        #sio.connect('https://qp-master-server.herokuapp.com/')
        socketConnection()
    except spotipy.exceptions.SpotifyException as e:
        # Check for "device not found" error
        if e.http_status == 404 and "Device not found" in str(e):
            print("Device not found. Restarting spotifyd...")
            restart_spotifyd()
            time.sleep(5)  # Wait for Spotifyd to restart
            
            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()
            
            print("Attempting to play song again...")
            playSong(trkArr, pos)
        else:
            raise
        
# ----------------------------------------------------------

# ----------------------------------------------------------
# Section 2: Client->Server + Client->Spotify Controls

def pushBPMToPlay(bpmAdded):
    songToBePlayed=requests.post(baseUrl+"getTrackToPlay", json={"bpm":bpmAdded, "clientID":clientID})

def pushBPMToQueue(bpmAdded):
    songToBeQueued=requests.post(baseUrl+"getTrackToQueue", json={"bpm":bpmAdded, "userID":clientID, "cln":cluster})

# read the tap once, record the timestamp
# increase or reset the tap count, depending on the interval
def TapBPM(): 
    global tapCount, msFirstTap, msLastTap, bpmAdded

    msCurr=int(time.time()*1000)

    if (msLastTap == 0 and tapCount == 0):
        print ("  # First tap")
        msLastTap=msCurr
        msFirstTap = msCurr
        tapCount = 1
    else:
        # take the running average of a series of taps
        #if msCurr-msFirstTap > 0:
        bpmAvg= 60000 * tapCount / (msCurr-msFirstTap)
        bpmAdded=round(round(bpmAvg*100)/100)
        tapCount+=1 
        msLastTap=msCurr
        print ("  # Next tap {}".format(tapCount))


# There is a new BPM that just came in, so notify the server to either play a song or add a song to the queue
def tapController():    
    global playingCheck, bpmAdded, msLastTap, tapCount, tapInterval

    while True:
            
        msCurr = int(time.time()*1000)

        try:
            # the last tap has happened more than 2 seconds ago -- finish recording
            if msCurr-msLastTap > 1000*tapInterval and bpmAdded > 0:
                print("   # LastTap Detected. BPM: {}".format(bpmAdded))
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
    global playingCheck, durationCheck
    
    try:
        devices = sp.devices()['devices']
        print(devices)
        sp.start_playback(device_id=device_id, uris=trkArr, position_ms=pos) 
    
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
            print("Device not found. Restarting spotifyd...")
            restart_spotifyd()
            time.sleep(5)  # Wait for Spotifyd to restart
            
            print("Disconnecting from server...")
            sio.disconnect()
            time.sleep(2)
            print("Reconnecting to server...")
            #sio.connect('https://qp-master-server.herokuapp.com/')
            socketConnection()
            
            print("Attempting to play song again...")
            playSong(trkArr, pos)
        else:
            raise
    
    sp.volume(currVol, device_id)   

    # indicate the song is now playing
    playingCheck=True
    # TODO: why is this set to True here?
    durationCheck=True

# def checkSpotifyConnection()
    # try:
        # devices = sp.devices()
    # except:
        
# A wrapper function to save information for cross-checking if the next song coming in is a new song 
# This prevents the same song from playing repeatedly
def playSongsToContinue(songDuration, songID, msg): 
    global playingCheck, prevDuration, prevID, cluster
    playingCheck=False
    prevDuration=songDuration
    prevID=songID
    continueSong=requests.get(baseUrl+"continuePlaying", json={"userID":clientID, "msg":msg, "cln":cluster})

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
    

# def colorArrayBuilder(lights):
    # global colorArrBefore, colorArrAfter, pixels
    # n = 0
    # print("inside colorArrayBuilder")
    # print(pixels[0])

    # for ring in lights:
        # print("for loop enters")
        # colors = lights[ring]["colors"]
        # newBPM = lights[ring]["rotate"]

        # divs = int(36 / len(colors))
        # rgb_vals = []
        # for i in colors:
            # rgb_vals.append((colors[i]["r"], colors[i]["g"], colors[i]["b"], colors[i]["w"]))
        
        # rotation_speed = 1  # Adjust the rotation speed as desired
        # offset = int(time.time() * 100 * rotation_speed) % 36  # Create a rotating offset based on time

        # for i in range(len(rgb_vals)):
            # colorArrAfter[n:n+divs] = interpolate_rgbw(rgb_vals[i], rgb_vals[(i+1) % len(rgb_vals)], divs)
            
            # for j in range(n, n + divs):
                # rotated_index = (j + offset) % 36
                # colorArrAfter[j] = colorArrAfter[rotated_index]

            # n += divs

    # # Check if color array is different to trigger fade in and out
    # if colorArrBefore != colorArrAfter:
        # print("if enters")
        # # Define the maximum brightness value
        # max_brightness = 255
        # fade_duration = 0.15  # Adjust the fade duration as desired

        # # Calculate the number of steps based on the fade duration and delay
        # num_steps = int(fade_duration / 0.01)

        # # Fade-out effect
        # if not (pixels[0] == [0,0,0,0]):
            # print("fade out")
            # for step in range(num_steps, -1, -1):
                # brightness = int(step * max_brightness / num_steps)
                # for i in range(144):
                    # pixels[i] = tuple(int(val * brightness / max_brightness) for val in colorArrBefore[i])
                # pixels.show()
                # time.sleep(0.01)

        # # Fade-in effect
        # print("fade in")
        # for step in range(num_steps + 1):
            # brightness = int(step * max_brightness / num_steps)
            # for i in range(144):
                # pixels[i] = tuple(int(val * brightness / max_brightness) for val in colorArrAfter[i])
            # pixels.show()
            # time.sleep(0.01)

        # colorArrBefore = copy.deepcopy(colorArrAfter)


def colorArrayBuilder(lights):
    global colorArrBefore, colorArrAfter, pixels
    n = 0
    print("inside colorArrayBuilder")
    print(pixels[0])

    for ring in lights:
        print("for loop enters")
        colors = lights[ring]["colors"]
        newBPM = lights[ring]["rotate"]
        
        # Check if "rotate" is True for the current ring
        if newBPM:
            dim_brightness = 50  # Adjust the dim brightness as needed
        else:
            dim_brightness = 255  # Full brightness for non-rotating rings
        
        divs = int(36 / len(colors))
        rgb_vals = []
        for i in colors:
            rgb_vals.append((colors[i]["r"], colors[i]["g"], colors[i]["b"], colors[i]["w"]))
        for i in range(len(rgb_vals)):
            colorArrAfter[n:n+divs] = interpolate_rgbw(rgb_vals[i], rgb_vals[(i+1) % len(rgb_vals)], divs)
            
            if newBPM:
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
    half_interval = interval / 4
    
    while playingCheck:
        start_time = time.time()
        
        for i in range(144, 160):
            pixels[i] = ringColor
        pixels.show()
        
        time.sleep(half_interval)
        
        for i in range(144, 160):
            pixels[i] = (0, 0, 0, 0)
        pixels.show()
        
        elapsed_time = time.time() - start_time
        sleep_time = interval - elapsed_time
        
        if sleep_time > 0:
            time.sleep(sleep_time)
            if elapsed_time >= interval:
                start_time = time.time()
        

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
    global prevDuration, prevID, startTime, totalTime, durationCheck, currSongID, seekCheck, seekedPlayer, seekedClient, currDuration, playback, currVol

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
                    except requests.exceptions.ReadTimeout:
                        print("Read timeout while checking for currently playing song")
                        print("Disconnecting from server...")
                        sio.disconnect()
                        time.sleep(2)
                        print("Reconnecting to server...")
                        #sio.connect('https://qp-master-server.herokuapp.com/')
                        socketConnection()

                    if(currSongItem):
                        durationCheck=False
                        print("Duration is set")
                        currDuration=currSongItem['duration_ms']
                        currSongID=currSongItem['id']

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
                    if prevDuration==currDuration or prevID==currSongID:
                            print("Forcing to Continue")
                            print("prevID", prevID)
                            print("currID",currSongID)
                            playSongsToContinue(currDuration, currSongID, "Immediate")

                    # if the total time in the song is within the last 10s of the song,
                    # prepare to move on to the next song
                    if totalTime-seekedClient<=10000:
                        print("Fading out")
                        try:
                            playback = sp.current_playback()
                        except requests.exceptions.ReadTimeout:
                            print("Read timeout while checking for current playback state")
                            print("Disconnecting from server...")
                            sio.disconnect()
                            time.sleep(2)
                            print("Reconnecting to server...")
                            #sio.connect('https://qp-master-server.herokuapp.com/')
                            socketConnection()
                            
                        if playback != None and playback['device'] != None:
                            currVol = playback['device']['volume_percent']
                        # volume fades out
                        currVol=currVol*0.95
                        sp.volume(int(currVol), device_id)  
                        #else:
                        #    currVolume = currVolume

                    # if the song reaches the end (within the last 2s), end the song
                    if totalTime-elapsed_time<=2000:
                        print("Song has ended")
                        seekedPlayer=0
                        playSongsToContinue(currDuration,currSongID, "Normal")          
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
    global lights,lightCheck
    
    try:
        while True:
            if(lightCheck):
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
    global lights, ringLightCheck, playingCheck
    
    try:
        while True:
            if(ringLightCheck and playingCheck):
                ringLightUpdate(lights["ring1"]["rlight"], lights["ring1"]["bpm"])
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
    global clientStates
    
    try:
        while True:
            # if len(clientStates) > 0:
            #     print("clientStates in indicatorLightController:", clientStates)  # Debug print
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
    except TimeoutError:
        print("Timeout Error in indicatorLightController")

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


    # ----------------------------------------------------------
    # Section 5: Socket Controls   

    sio = socketio.Client()
    print("trying to connect")

    @sio.event
    def connect():
        global serverConnCheck, clientID, device_id, sp
        
        serverConnCheck = True
        print('Connected to server')
        sio.emit('connect_user',{"userID":2})
        
        #Client essential variables
        client_id='aeeefb7f628b41d0b7f5581b668c27f4'
        client_secret='7a75e01c59f046888fa4b99fbafc4784'
        spotify_username='x8eug7lj2opi0in1gnvr8lfsz'
        device_id='651d47833f4c935fadd4a03e43cd5a4c3ec0d170' #raspberry pi ID
        #device_id = '4cb43e627ebaf5bbd05e96c943da16e6fac0a2c5' #web player ID
        spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing,user-read-playback-state'
        spotify_redirect_uri = 'http://localhost:8000/callback'
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, scope=spotify_scope, username=spotify_username, requests_session=True, requests_timeout=None, open_browser=True))

        
    @sio.event
    def disconnect():
        print('Disconnected from server')

    @sio.event
    def message(data):
        global playingCheck, currSongID,seekCheck,seekedPlayer,lights,lightCheck, ringLightCheck, clientStates, cluster

        json_data = json.loads(data) # incoming message is transformed into a JSON object
        print("Server Sent the JSON:")
        print(json.dumps(json_data, indent = 2))

        if(json_data["msg"]!="Initial"):
            clientStates = json_data["activeUsers"]
        
        print(json_data["activeUsers"][clientID-1])
        if(json_data["activeUsers"][clientID-1]==True):
            if(json_data["msg"]=="Active" or json_data["msg"]=="Queue" or json_data["msg"]=="Song" or json_data["msg"]=="Backup"):
                #colorArrayBuilder(json_data["lights"])
                lights=json_data["lights"]
                lightCheck=True
                ringLightCheck = True
                clientStates = json_data["activeUsers"]

                print(bpmCountCheck)
                print(json_data["msg"])
                if(json_data["msg"]=="Song" and bpmCountCheck):
                    cluster = json_data["songdata"]["cluster_number"]
                    print("playing song")
                    try:
                        playSong(["spotify:track:"+json_data["songdata"]["songID"]],json_data["songdata"]["timestamp"])
                    except Exception as e:
                        print(f"An error occurred in the message thread: {str(e)}")
            elif(json_data["msg"]=="Seeking"):
                if playingCheck:
                    print("Updating seek")
                    try:
                        currSeeker=sp.currently_playing()
                    except requests.exceptions.ReadTimeout:
                        print("Minor Setback, Continue Continue")
                        print("Disconnecting from server...")
                        sio.disconnect()
                        time.sleep(2)
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
                    playSong(["spotify:track:"+json_data["songdata"]["songID"]],json_data["songdata"]["timestamp"])
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

