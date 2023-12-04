# Python libraries for Queue Player Software
import keyboard
from pynput.keyboard import Key
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
# import board
# import neopixel
# import RPi.GPIO as GPIO
# import busio
# import adafruit_ads1x15.ads1015 as ADS
# from adafruit_ads1x15.analog_in import AnalogIn

#Setup for potentiometer and piezo ADC channels 
# i2c = busio.I2C(board.SCL, board.SDA)
# ads = ADS.ADS1015(i2c)
# #chan_piezo = AnalogIn(ads, ADS.P0)  #piezo connected to pin A0 
# chan_pot = AnalogIn(ads, ADS.P0) #potentiometer connected to pin A1

# #Variables to tune and adjust piezo sensitivity 
# # THRESHOLD = 0.8  # Adjust this value based on your piezo sensitivity
# # DEBOUNCE_TIME = 0.1  # Adjust this value based on min. time needed between consecutive taps
# THRESHOLD = 0.5  # Adjust this value based on your piezo sensitivity
# DEBOUNCE_TIME = 0.1  # Adjust this value based on min. time needed between consecutive taps

# #Neopixel Setup for strip and ring light 
# pixel_pin1 = board.D12 # the pin to which the LED strip is connected to
# pixel_pin2 = board.D10 # the pin to which the ring light is connected to
# num_pixels = 160 # this specifies the TOTAL number of pixels (should be a multiple of 12. ie. 12, 24, 36, 48 etc)
# num_ring_pixels = 16
# ORDER = neopixel.GRBW # set the color type of the neopixel
# ledSegment = 36 # number of LEDs in a single segment
# ledArray = [[[0 for i in range(4)] for j in range(ledSegment)] for z in range(4)] #the array which stores the pixel information

# # #Create and initiate neopixel objects
# pixels = neopixel.NeoPixel(pixel_pin1, num_pixels, brightness=10, auto_write=False, pixel_order=ORDER)
# ring_pixels = neopixel.NeoPixel(pixel_pin2, num_ring_pixels, brightness = 10, auto_write = False, pixel_order=ORDER)

# #Indicator Light Setup
# GPIO.setup(23,GPIO.OUT)
# GPIO.setup(24,GPIO.OUT)
# GPIO.setup(25,GPIO.OUT)


# #Tap Sensor Setup
# channel = 17
# GPIO.setmode(GPIO.BCM)
# GPIO.setup(channel, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)

# ----------------------------------------------------------

#Client essential variables
# clientID=2
#     #[OLO4 : QP Client Credentials]
# client_id='aeeefb7f628b41d0b7f5581b668c27f4'
# client_secret='7a75e01c59f046888fa4b99fbafc4784'
# spotify_username='x8eug7lj2opi0in1gnvr8lfsz'
# device_id='651d47833f4c935fadd4a03e43cd5a4c3ec0d170' #raspberry pi ID
# #device_id = '4cb43e627ebaf5bbd05e96c943da16e6fac0a2c5' #web player ID
# spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing,user-read-playback-state'
# spotify_redirect_uri = 'http://localhost:8000/callback'
# sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, scope=spotify_scope, username=spotify_username, requests_session=True, requests_timeout=None, open_browser=True))

# #Client essential variables
# clientID=4
# #[OLO2 Credentials]
# client_id='bdfdc0993dcc4b9fbff8aac081cad246'
# client_secret='969f0ef8c11d49429e985aab6dd6ff0c'
# spotify_username='7w8j8bkw92mlnz5mwr3lou55g'
# #device_id='651d47833f4c935fadd4a03e43cd5a4c3ec0d170'
# #device_id = '217a37cc1f6f9c7937afbfa6f50424b7d937620f'
# device_id = '3946ec2b810ec4e30489b4704e9a695b1a64da26'
# spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing, user-read-playback-state'
# spotify_redirect_uri = 'http://localhost:8000'
# sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, scope=spotify_scope, username=spotify_username, requests_session=True, requests_timeout=None, open_browser=True))
# #sp.devices()

# #Client essential variables
# clientID=3
# #[OLO3 Credentials]
# client_id='0cf223c8598244998b098c8c8daf401a'
# client_secret='a68180a8aff04e4fb3fe2c5834b86ff0'
# spotify_username='qjczeruw4padtyh69nxeqzohi'
# device_id = '6b5d83a142591f256666bc28a3eccb56258c5dc7'
# spotify_scope='user-library-read, user-modify-playback-state, user-read-currently-playing, user-read-playback-state'
# spotify_redirect_uri = 'https://example.com/callback/'
# sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, scope=spotify_scope, username=spotify_username, requests_session=True, requests_timeout=None, open_browser=False))
# #print(sp.devices())

clientID=1
device_id=None
sp=None

#Global check variables 
bpmTapCheck=False
bpmCountCheck=False
playingCheck=False
seekCheck=False
newCheck=False
durationCheck=True
lightCheck = False
lights = None 
rotation = None
rotationCheck = False
ringLightCheck = False
fadeToBlackCheck = False
serverConnCheck = False

clientStates = []

#BPM function variables
bpmAdded=215
tapCount=0
msFirst=0
msPrev=0

#Server Variable
baseUrl="https://qp-master-server.herokuapp.com/"

#Global volume variables 
prevVal = 0 #previous value for volume
currVol = 100 #current value for volume

#Lights function variables
colorArrBefore=[(0,0,0,0)]*144
colorArrAfter=[0]*144

#Global seek variable
seekedPlayer=0

#Global idling fail-safe variable
prevID=''
prevDuration=0
currSongID=''
currDuration=None

# Local timer variables for song end check
startTime=None
totalTime=None
seekedClient=0

#playback variable to keep a check
playback=None

# Function to restart spotifyd
def restart_spotifyd():
    try:
        subprocess.run(["sudo", "pkill", "spotifyd"]) # Kill existing spotifyd processes
        subprocess.run(["/home/pi/spotifyd", "--no-daemon", "--config-path", "/home/pi/.config/spotifyd/spotifyd.conf"]) # Restart spotifyd (check if this is the correct path)
    except Exception as e:
        print(f"An error occurred while restarting Spotifyd: {str(e)}")

def restart_script():
    # Add any cleanup or state reset logic here
    time.sleep(5)  # Optional delay before restarting to avoid immediate restart loop
    print("Restarting the script...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

# ----------------------------------------------------------
# Section 1 : Client States Control

def setClientActive():
    global clientID
    setClientActive=requests.post(baseUrl+"setClientActive", json={"clientID":clientID})

def setClientInactive():
    global clientID
    setClientInactive=requests.post(baseUrl+"setClientInactive", json={"clientID":clientID})

def infiniteloop3():
    global bpmCountCheck,prevVal,currVol,playingCheck, currSongID, seekedClient, durationCheck, fadeToBlackCheck
    
    #Voltage variables
    window_size = 4
    voltage_readings = [0] * window_size  # Initialize with zeros
    
    try:
    # Inside your main loop where you read the potentiometer voltage
        while True:
            # Read potentiometer voltage
            # current_voltage = chan_pot.voltage

            # Update moving average readings
            # voltage_readings.append(current_voltage)
            # if len(voltage_readings) > window_size:
                # voltage_readings.pop(0)  # Remove the oldest reading

            # Calculate the moving average
            #filtered_voltage = moving_average(voltage_readings)
            # filtered_voltage = current_voltage
            #print(filtered_voltage)

            if keyboard.is_pressed("o"):
            # if filtered_voltage < 0.03:
                if playingCheck and bpmCountCheck:
                    playingCheck=False
                    bpmCountCheck=False
                    sp.pause_playback(device_id=device_id) # will give the error for spotify command failed have to incorporate similar mechanism as volume
                    setClientInactive()
                    seekData=requests.post(baseUrl+"updateSeek", json={"seek":seekedClient+seekedPlayer, "song":currSongID,"prompt":"Continue"})
                    print("Client is set Inactive")
                    fadeToBlackCheck = True
                

            elif keyboard.is_pressed("s"):
            # elif filtered_voltage > 0.1 and not bpmCountCheck and serverConnCheck:
                #currVol = int (map_to_volume(chan_pot.voltage)) #set current volume to potentiometer value
                # currVol = int(map_to_volume(filtered_voltage))
                bpmCountCheck=True
                setClientActive()
                checkBPMAdded()
                print("Client is set Active")
                print("Press enter for BPM")

            # have this as a seperate thread maybe just to have better code modularity, no point being here anyways
            if bpmCountCheck and playingCheck:
                #currVol = int (map_to_volume(chan_pot.voltage)) 
                # currVol = int(map_to_volume(filtered_voltage))
                #print(currVol)
                if(abs(prevVal-currVol) >= 5):
                    try:
                        sp.volume(currVol, device_id)
                    except:
                        print("Timeout while changing volume")
                    prevVal = currVol
                    print("changing volume")
    
    except KeyboardInterrupt:
        print("Interrupted by Keyboard, script terminated")

        sio.disconnect()
        time.sleep(2)
        sio.connect()
        
# def infiniteloop3():
    # global bpmCountCheck,prevVal,currVol,playingCheck, currSongID, seekedClient, durationCheck

    # while True:
        # #if keyboard.is_pressed("o"):
        # if chan_pot.voltage < 0.1:
            # if playingCheck and bpmCountCheck:
                # playingCheck=False
                # bpmCountCheck=False
                # sp.pause_playback(device_id=device_id) # will give the error for spotify command failed have to incorporate similar mechanism as volume
                # setClientInactive()
                # seekData=requests.post(baseUrl+"updateSeek", json={"seek":seekedClient+seekedPlayer, "song":currSongID,"prompt":"Continue"})
                # print("Client is set Inactive")
                # #pixels.fill((0,0,0,0))
                # #pixels.show()
                # fadeToBlack()
            

        # #elif keyboard.is_pressed("s"):
        # elif chan_pot.voltage > 0.2 and not bpmCountCheck and serverConnCheck:
            # currVol = int (map_to_volume(chan_pot.voltage)) #set current volume to potentiometer value
            # bpmCountCheck=True
            # setClientActive()
            # checkBPMAdded()
            # print("Client is set Active")
            # print("Press enter for BPM")

        # if bpmCountCheck and playingCheck:
            # currVol = int (map_to_volume(chan_pot.voltage))
            # #print(currVol)
            # if(abs(prevVal-currVol) >= 5):
                # sp.volume(currVol, device_id)
                # prevVal = currVol
                # print("changing volume")

# ----------------------------------------------------------

# ----------------------------------------------------------
# Section 2 : Client->Server + Client->Spotify Controls

def pushBPMToPlay():
    songToBePlayed=requests.post(baseUrl+"getTrackToPlay", json={"bpm":bpmAdded, "clientID":clientID})

def pushBPMToQueue():
    songToBeQueued=requests.post(baseUrl+"getTrackToQueue", json={"bpm":bpmAdded, "userID":clientID})

def TapBPM(): 
    global tapCount,msFirst,msPrev,bpmAdded,bpmTapCheck

    msCurr=int(time.time()*1000)
    if(msCurr-msPrev > 1000*2):
        tapCount = 0

    if(tapCount == 0):
        msFirst = msCurr
        tapCount = 1
    else:
        if msCurr-msFirst > 0:
            #bpmAvg= 60000 * tapCount / (msCurr-msFirst)
            bpmAvg= 60000 * tapCount / (msCurr-msFirst)
            bpmAdded=round(round(bpmAvg*100)/100)
        # bpmAdded=137
        tapCount+=1 

    msPrev=msCurr
    bpmTapCheck=True

def checkBPMAdded():    
    global playingCheck,bpmTapCheck, bpmAdded, bpmCountCheck, bpmTimer

    msCurr=int(time.time()*1000)
    if bpmTapCheck==True and msCurr-msPrev>1000*2:
        if playingCheck:
            pushBPMToQueue()
        else:
            pushBPMToPlay()
        
        bpmTapCheck=False
    
    if bpmCountCheck:
        bpmTimer=Timer(2,checkBPMAdded)
        bpmTimer.start()
    else:
        bpmTimer.cancel()

def playSong(trkArr, pos):
    global playingCheck, durationCheck
    try:
        sp.start_playback(device_id=device_id, uris=trkArr, position_ms=pos) 
    except requests.exceptions.ConnectTimeout:
        print("Connection timeout while playing a song")

        sio.disconnect()
        time.sleep(2)
        sio.connect()
    except requests.exceptions.ReadTimeout:
        print("Read timeout while playing a song")

        sio.disconnect()
        time.sleep(2)
        sio.connect()

    #Last Resort is to restart script
    # except requests.exceptions.ReadTimeout:
        # print("Minor Setback. Restarting the script...")
        # restart_script()

    #Restart spotifyd with credentials if device is not found
    except spotipy.exceptions.SpotifyException as e:
        # Check for "device not found" error
        if e.http_status == 404 and "Device not found" in str(e):
            print("Device not found. Restarting spotifyd...")
            restart_spotifyd()
            time.sleep(5)  # Wait for Spotifyd to restart
            playSong(trkArr, pos)
        else:
            raise
            
    sp.volume(currVol, device_id)   
    playingCheck=True
    durationCheck=True

def playSongsToContinue(songDuration, songID, msg): 
    global playingCheck,prevDuration, prevID
    playingCheck=False
    prevDuration=songDuration
    prevID=songID
    continueSong=requests.get(baseUrl+"continuePlaying", json={"userID":clientID,"msg":msg})


def infiniteloop1():
    while True:
        try:
            if bpmCountCheck:
                value = input()
                if(value==""):
                    TapBPM()
        except KeyboardInterrupt:
            print("Interrupted by Keyboard, script terminated")

            sio.disconnect()
            time.sleep(2)
            sio.connect()

            
# def infiniteloop1(channel):
    
#     debounce_time = 0.05
#     current_time = time.time()

#     if (current_time - infiniteloop1.last_time) > debounce_time:
#         if GPIO.input(channel):
#             TapBPM()
#             print("Tap")
#         infiniteloop1.last_time = current_time

# infiniteloop1.last_time = time.time()

# GPIO.add_event_detect(channel, GPIO.BOTH, callback=infiniteloop1, bouncetime=5)
#     # if GPIO.input(channel):
#             # TapBPM()
#             # print ("Tap")

# #GPIO.add_event_detect(channel, GPIO.BOTH, bouncetime=50)  # let us know when the pin goes HIGH or LOW
# GPIO.add_event_detect(channel, GPIO.BOTH)  # let us know when the pin goes HIGH or LOW
# GPIO.add_event_callback(channel, infiniteloop1)  # assign function to GPIO PIN, Run function on change



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
# Section 3 : NeoPixel & Ring Light Control

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
        

def fadeToBlack(lights):
    global pixels # Make sure 'pixels' is a global variable
    global colorArrBefore

    # Define the maximum brightness value
    max_brightness = 255
    fade_duration = 0.15  # Adjust the fade duration as desired

    # Calculate the number of steps based on the fade duration and delay
    num_steps = int(fade_duration / 0.01)

    # Fade-out effect
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

# ----------------------------------------------------------
# Section 4 : Timer Controls     

def infiniteloop2():
    global prevDuration, prevID, startTime ,totalTime, durationCheck, currSongID, seekCheck, seekedPlayer,seekedClient, currDuration, playback

    try:
        while True:
            if playingCheck: 
                if(durationCheck):
                    print("Duration Checking")
                    try:
                        currSongItem = sp.currently_playing()['item']
                    except requests.exceptions.ReadTimeout:
                        print("Read timeout while checking for currently playing song")

                    if(currSongItem):
                        durationCheck=False
                        print("Duration set")
                        currDuration=currSongItem['duration_ms']
                        currSongID=currSongItem['id']
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
                    if totalTime-seekedClient<=10000:
                        print("Fading out")
                        try:
                            playback = sp.current_playback()
                        except requests.exceptions.ReadTimeout:
                            print("Read timeout while checking for current playback state")
                        if playback != None and playback['device'] != None:
                            currVolume = playback['device']['volume_percent']
                        currVolume=currVolume*0.95
                        sp.volume(int(currVolume), device_id)  
                        #else:
                        #    currVolume = currVolume
                    
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
        sio.connect()

# ----------------------------------------------------------

def moving_average(values):
    return sum(values) / len(values)
    
    

# def infiniteloop4():
#     global lights,lightCheck
#     while True:
#         if(lightCheck):
#             #print("color should be updating")
#             colorArrayBuilder(lights)
#             #showNewBPM(lights)
#             lightCheck=False
            

# def infiniteloop5():
#     global lights, ringLightCheck, playingCheck
#     while True:
#         if(ringLightCheck and playingCheck):
#             ringLightUpdate(lights["ring1"]["rlight"], lights["ring1"]["bpm"])
#             ringLightCheck=False

# def infiniteloop6():
#    global clientStates

#    while True:
#         # if len(clientStates) > 0:
#         #     print("clientStates in infiniteloop6:", clientStates)  # Debug print
#         if(len(clientStates) > 0 and clientStates[0] == True): #Yellow QP
#             GPIO.output(23,GPIO.HIGH)
#             #print("Yellow QP Active")
#         else:
#             GPIO.output(23,GPIO.LOW)
            
#         if(len(clientStates) > 0 and clientStates[2] == True): #Violet QP
#             GPIO.output(24,GPIO.HIGH)
#             #print("Violet QP Active")
#         else:
#             GPIO.output(24,GPIO.LOW)

#         if(len(clientStates) > 0 and clientStates[3] == True): #Orange QP
#             GPIO.output(25,GPIO.HIGH)
#             #print("Orange QP Active")
#         else:
#             GPIO.output(25,GPIO.LOW)
            

# def infiniteloop7():
#     global fadeToBlackCheck
#     while True:
#         if(fadeToBlackCheck):
#             print("fading to black")
#             fadeToBlack()
#             fadeToBlackCheck = False


# thread1 = threading.Thread(target=infiniteloop1(channel))
# thread1.start()

thread1 = threading.Thread(target=infiniteloop1)
thread1.start()

thread2 = threading.Thread(target=infiniteloop2)
thread2.start()

thread3 = threading.Thread(target=infiniteloop3)
thread3.start()

# thread4 = threading.Thread(target=infiniteloop4)
# thread4.start()

# thread5 = threading.Thread(target=infiniteloop5)
# thread5.start()

# thread6 = threading.Thread(target=infiniteloop6)
# thread6.start()

# thread7 = threading.Thread(target=infiniteloop7)
# thread7.start()


# ----------------------------------------------------------
# Section 5 : Socket Controls   

sio = socketio.Client()

@sio.event
def connect():
    global serverConnCheck, clientID, device_id, sp
    
    serverConnCheck = True
    print('Connected to server')
    sio.emit('connect_user',{"userID":2})
    
    #potentially add ringlight feedback for not connecting 
    # [OLO5 Credentials]
    # Client essential variables
    client_id='765cacd3b58f4f81a5a7b4efa4db02d2'
    client_secret='cb0ddbd96ee64caaa3d0bf59777f6871'
    spotify_username='n39su59fav4b7fmcm0cuwyv2w'
    device_id='1632b74b504b297585776e716b8336510639401a'
    spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing,user-read-playback-state'
    spotify_redirect_uri = 'http://localhost:8000/callback'
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, scope=spotify_scope, username=spotify_username, requests_session=True, requests_timeout=None, open_browser=True))

@sio.event
def disconnect():
    print('Disconnected from server')

@sio.event
def message(data):
    global playingCheck, currSongID,seekCheck,seekedPlayer,lights,lightCheck, ringLightCheck, clientStates

    json_data = json.loads(data) # incoming message is transformed into a JSON object
    print("Server Sent the JSON:")
    print(json.dumps(json_data, indent = 2))

    if(json_data["msg"]!="Initial"):
        clientStates = json_data["activeUsers"]


    if(json_data["msg"]=="Active" or json_data["msg"]=="Queue" or json_data["msg"]=="Song" or json_data["msg"]=="Backup"):
        #colorArrayBuilder(json_data["lights"])
        lights=json_data["lights"]
        lightCheck=True
        ringLightCheck = True

        print(bpmCountCheck)
        print(json_data["msg"])
        if(json_data["msg"]=="Song" and bpmCountCheck):
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
            seekData=requests.post(baseUrl+"updateSeek", json={"seek":currSeeker['progress_ms'], "song":currSeeker['item']['id'],"prompt":"Bro"})
    elif(json_data["msg"]=="SeekSong"):
        if not playingCheck and bpmCountCheck:
            print("This is the new client")
            seekCheck=True
            seekedPlayer=json_data["songdata"]["timestamp"]
            print("json retrieved")
            playSong(["spotify:track:"+json_data["songdata"]["songID"]],json_data["songdata"]["timestamp"])
            print("playsong")

            lights=json_data["lights"]
            lightCheck=True
            ringLightCheck = True

    print("///////////////////////////////////////////////////////////////////////////////////////////////////////////")

sio.connect('https://qp-master-server.herokuapp.com/')
sio.wait()

# ----------------------------------------------------------

