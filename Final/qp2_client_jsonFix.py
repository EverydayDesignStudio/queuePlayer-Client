#import keyboard
#from pynput.keyboard import Key
import copy
import threading
from threading import Timer
import time
import math
import requests
import socketio
import json 
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException


import board
import neopixel
import RPi.GPIO as GPIO
import busio
import adafruit_ads1x15.ads1015 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# #Setup for potentiometer and piezo ADC channels 
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1015(i2c)
#chan_piezo = AnalogIn(ads, ADS.P0)  #piezo connected to pin A0 
chan_pot = AnalogIn(ads, ADS.P0) #potentiometer connected to pin A1

# #Variables to tune and adjust piezo sensitivity 
THRESHOLD = 0.8  # Adjust this value based on your piezo sensitivity
DEBOUNCE_TIME = 0.1  # Adjust this value based on min. time needed between consecutive taps

# #Neopixel Setup for strip and ring light 
pixel_pin1 = board.D12 # the pin to which the LED strip is connected to
pixel_pin2 = board.D10 # the pin to which the ring light is connected to
num_pixels = 160 # this specifies the TOTAL number of pixels (should be a multiple of 12. ie. 12, 24, 36, 48 etc)
num_ring_pixels = 16
ORDER = neopixel.GRBW # set the color type of the neopixel
ledSegment = 36 # number of LEDs in a single segment
ledArray = [[[0 for i in range(4)] for j in range(ledSegment)] for z in range(4)] #the array which stores the pixel information

# #Create and initiate neopixel objects
pixels = neopixel.NeoPixel(pixel_pin1, num_pixels, brightness=0.4, auto_write=False, pixel_order=ORDER)
ring_pixels = neopixel.NeoPixel(pixel_pin2, num_ring_pixels, brightness = 0.4, auto_write = False, pixel_order=ORDER)

#Indicator Light Setup
GPIO.setup(23,GPIO.OUT)
GPIO.setup(24,GPIO.OUT)
GPIO.setup(25,GPIO.OUT)


#Tap Sensor Setup
channel = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(channel, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)

#Client essential variables
clientID=2
    #[OLO4 : QP Client Credentials]
client_id='aeeefb7f628b41d0b7f5581b668c27f4'
client_secret='7a75e01c59f046888fa4b99fbafc4784'
spotify_username='x8eug7lj2opi0in1gnvr8lfsz'
device_id='651d47833f4c935fadd4a03e43cd5a4c3ec0d170'
spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing,user-read-playback-state'
spotify_redirect_uri = 'http://localhost:8000/callback'
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, scope=spotify_scope, username=spotify_username, requests_session=True, requests_timeout=None, open_browser=True))

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


def setClientActive():
    global clientID

    setClientActive=requests.post(baseUrl+"setClientActive", json={"clientID":clientID})

def setClientInactive():
    global clientID
    
    setClientInactive=requests.post(baseUrl+"setClientInactive", json={"clientID":clientID})

def pushBPMToPlay():
    songToBePlayed=requests.post(baseUrl+"getTrackToPlay", json={"bpm":bpmAdded, "clientID":clientID})

def pushBPMToQueue():
    songToBeQueued=requests.post(baseUrl+"getTrackToQueue", json={"bpm":bpmAdded, "userID":clientID})

def playSong(trkArr, pos):
    global playingCheck, durationCheck

    sp.start_playback(device_id=device_id, uris=trkArr, position_ms=pos)
    sp.volume(currVol, device_id)   
    playingCheck=True
    durationCheck=True


def playSongsToContinue(songDuration, songID, msg): 
    global playingCheck,prevDuration, prevID

    playingCheck=False
    prevDuration=songDuration
    prevID=songID
    continueSong=requests.get(baseUrl+"continuePlaying", json={"userID":clientID,"msg":msg})

# def seekToPlay():
#     global seekedPlayer, seekCheck

#     playerSeek=requests.get(baseUrl+"getSeek")
#     if(playerSeek.json()['seek']>=0):
#         trackArr=[]
#         trackArr.append("spotify:track:"+playerSeek.json()['id'])
#         seekedPlayer=playerSeek.json()['seek']
#         playSong(trackArr,seekedPlayer)
#         seekCheck=True

#function to calculate BPM input
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

#function to periodically check the client state to indicate when a bpm is added
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
    global colorArrBefore, colorArrAfter
    n = 0
    print("inside colorArrayBuilder")
    print(pixels[0])

    for ring in lights:
        colors = lights[ring]["colors"]
        divs = int(36 / len(colors))
        rgb_vals = []
        for i in colors:
            rgb_vals.append((colors[i]["r"], colors[i]["g"], colors[i]["b"], colors[i]["w"]))
        for i in range(len(rgb_vals)):
            colorArrAfter[n:n+divs] = interpolate_rgbw(rgb_vals[i], rgb_vals[(i+1) % len(rgb_vals)], divs)
            n += divs

    # Check if color array is different to trigger fade in and out
    if colorArrBefore != colorArrAfter:
        # Define the maximum brightness value
        max_brightness = 255
        fade_duration = 0.15 # Adjust the fade duration as desired

        # Calculate the number of steps based on the fade duration and delay
        num_steps = int(fade_duration / 0.01)

        # Fade-out effect
        if not (pixels[0] == [0,0,0,0]):
            for step in range(num_steps, -1, -1):
                brightness = int(step * max_brightness / num_steps)
                for i in range(144):
                    pixels[i] = colorArrBefore[i]
                pixels.brightness = brightness / max_brightness
                pixels.show()
                time.sleep(0.01)

        # Fade-in effect
        for step in range(num_steps + 1):
            brightness = int(step * max_brightness / num_steps)
            for i in range(144):
                pixels[i] = colorArrAfter[i]
            pixels.brightness = brightness / max_brightness
            pixels.show()
            time.sleep(0.01)

        colorArrBefore = copy.deepcopy(colorArrAfter)

# def lerp(a, b, t):
#     return a + (b - a) * t

# def ringLightUpdate(ringColor, bpm):
#     # for i in range(144, 160):  # Indices for the last 16 LEDs
#     #     pixels[i] = ringColor
#     # pixels.show()
#     global playingCheck

#     interval = 60 / bpm  # Calculate the time interval between beats
#     start_time = time.time()

#     print(ringColor)
#     print(bpm)
    
#     while True:

#         if not playingCheck:
#             break
#         else:
#             elapsed_time = time.time() - start_time
#             t = (elapsed_time % interval) / interval  # Calculate a value between 0 and 1

#             brightness = lerp(0, 1, t)

#             # Calculate the color with adjusted brightness
#             adjusted_color = tuple(int(c * brightness) for c in ringColor)

#             # Update NeoPixels
#             for i in range(144, 160):
#                 pixels[i] = adjusted_color
#             pixels.show()

#             time.sleep(0.005)  # Small delay for smoother animation
def ringLightUpdate(ringColor, bpm):
    global playingCheck

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

# def ringLightUpdate(ringColor, bpm):
#     global playingCheck

#     interval = 60 / bpm  # Calculate the time interval between beats
#     num_steps = 3  # Number of steps for intensity adjustment
    
#     print(ringColor)
#     print(bpm)

#     while playingCheck:
#         for step in range(num_steps):
#             intensity = step / (num_steps - 1)
#             adjusted_color = tuple(int(c * intensity) for c in ringColor)
            
#             for i in range(144, 160):
#                 pixels[i] = adjusted_color
#             pixels.show()
            
#             time.sleep(interval / (num_steps * 4))
            
#         for step in range(num_steps - 1, -1, -1):
#             intensity = step / (num_steps - 1)
#             adjusted_color = tuple(int(c * intensity) for c in ringColor)
            
#             for i in range(144, 160):
#                 pixels[i] = adjusted_color
#             pixels.show()
            
#             time.sleep(interval / (num_steps * 4))

# Function to calculate time interval (in seconds) between each pulse
# def calculate_pulse_interval(bpm):
#     return 60.0 / bpm

# def pulse_neopixels(lights):
#     # Loop through each ring in the lights dictionary
#     for ring_name, ring_info in lights.items():
#         # Check if the current ring has "rotate" set to true
#         rotation = ring_info.get("rotate", False)

#         if rotation:
#             bpm = ring_info.get("bpm", 60)  # Default BPM is 60 if not provided
#             colors = ring_info.get("colors", [])  # RGBW colors list for the ring

#             # Calculate time interval (in seconds) between each pulse
#             pulse_interval = calculate_pulse_interval(bpm)

#             # Determine the range of pixels to pulse based on the ring (section)
#             section_start = 0
#             section_end = len(colors)

#             if ring_name == "ring1":
#                 section_start = 0
#                 section_end = 36
#             elif ring_name == "ring2":
#                 section_start = 36
#                 section_end = 72
#             elif ring_name == "ring3":
#                 section_start = 72
#                 section_end = 108
#             elif ring_name == "ring4":
        #         section_start = 108
        #         section_end = 144

        #     # Start pulsing effect for the current ring (section)
        #     while rotation:
        #         for i in range(section_start, section_end):
        #             for j in range(0, 256, 5):  # Pulsing intensity (0-255) with a step of 5
        #                 # Set the color of the current pixel with pulsing intensity
        #                 pixels[i] = (
        #                     (colors[i - section_start][0] * j) // 255,
        #                     (colors[i - section_start][1] * j) // 255,
        #                     (colors[i - section_start][2] * j) // 255,
        #                     colors[i - section_start][3],
        #                 )
        #             pixels.show()
        #             time.sleep(pulse_interval)

        # else:
        #     # Set the static colors for the non-rotating ring
        #     colors = ring_info.get("colors", [])
        #     for i in range(len(colors)):
        #         pixels[i] = colors[i]
        #     pixels.show()

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
    
def fadeToBlack():
          # Define the maximum brightness value
        max_brightness = 255
        fade_duration = 0.15 # Adjust the fade duration as desired

        # Calculate the number of steps based on the fade duration and delay
        num_steps = int(fade_duration / 0.01)

        # Fade-out effect
        #if not (pixels[0] == [0,0,0,0]):
        for step in range(num_steps, -1, -1):
            brightness = int(step * max_brightness / num_steps)
            for i in range(144):
                pixels[i] = [0,0,0,0]
            pixels.brightness = brightness / max_brightness
            pixels.show()
            time.sleep(0.01)

# def infiniteloop1():
#     while True:
#         value = input()
#         if(value==""):
#             TapBPM()

def infiniteloop1(channel):
    if GPIO.input(channel):
            TapBPM()
            print ("Tap")

GPIO.add_event_detect(channel, GPIO.BOTH, bouncetime=50)  # let us know when the pin goes HIGH or LOW
GPIO.add_event_callback(channel, infiniteloop1)  # assign function to GPIO PIN, Run function on change


def infiniteloop2():
    global prevDuration, prevID, startTime ,totalTime, durationCheck, currSongID, seekCheck, seekedPlayer,seekedClient, currDuration

    while True:
        if playingCheck: 
            if(durationCheck):
                print("Duration Checking")
                currSongItem = sp.currently_playing()['item']
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
                    playback = sp.current_playback()
                    if playback['device'] != None:
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

def infiniteloop3():
    global bpmCountCheck,prevVal,currVol,playingCheck, currSongID, seekedClient, durationCheck

    while True:
        #if keyboard.is_pressed("o"):
        if chan_pot.voltage < 0.04:
            if playingCheck and bpmCountCheck:
                playingCheck=False
                bpmCountCheck=False
                sp.pause_playback(device_id=device_id) # will givw the error for spotify command failed have to incorporate similar mechanism as volume
                setClientInactive()
                seekData=requests.post(baseUrl+"updateSeek", json={"seek":seekedClient+seekedPlayer, "song":currSongID,"prompt":"Continue"})
                print("Client is set Inactive")
                #pixels.fill((0,0,0,0))
                #pixels.show()
                fadeToBlack()
            

        #elif keyboard.is_pressed("s"):
        elif chan_pot.voltage > 0.1 and not bpmCountCheck and serverConnCheck:
            bpmCountCheck=True
            setClientActive()
            checkBPMAdded()
            print("Client is set Active")
            print("Press enter for BPM")

        if bpmCountCheck and playingCheck:
            currVol = int (map_to_volume(chan_pot.voltage))
            #print(currVol)
            if(abs(prevVal-currVol) >= 5):
                sp.volume(currVol, device_id)
                prevVal = currVol
                print("changing volume")

def infiniteloop4():
    global lights,lightCheck
    while True:
        if(lightCheck):
            print("color should be updating")
            colorArrayBuilder(lights)
            #ringLightUpdate(lights["ring1"]["rlight"], lights["ring1"]["bpm"])
            lightCheck=False

def infiniteloop5():
    global lights, ringLightCheck, playingCheck
    while True:
        if(ringLightCheck and playingCheck):
            ringLightUpdate(lights["ring1"]["rlight"], lights["ring1"]["bpm"])
            ringLightCheck=False

def infiniteloop6():
   global clientStates

   while True:
        # if len(clientStates) > 0:
        #     print("clientStates in infiniteloop6:", clientStates)  # Debug print
        if(len(clientStates) > 0 and clientStates[0] == True): #Yellow QP
            GPIO.output(23,GPIO.HIGH)
            #print("Yellow QP Active")
        else:
            GPIO.output(23,GPIO.LOW)
            
        if(len(clientStates) > 0 and clientStates[2] == True): #Violet QP
            GPIO.output(24,GPIO.HIGH)
            #print("Violet QP Active")
        else:
            GPIO.output(24,GPIO.LOW)

        if(len(clientStates) > 0 and clientStates[3] == True): #Orange QP
            GPIO.output(25,GPIO.HIGH)
            #print("Orange QP Active")
        else:
            GPIO.output(25,GPIO.LOW)


thread1 = threading.Thread(target=infiniteloop1(channel))
thread1.start()

# thread1 = threading.Thread(target=infiniteloop1)
# thread1.start()

thread2 = threading.Thread(target=infiniteloop2)
thread2.start()

thread3 = threading.Thread(target=infiniteloop3)
thread3.start()

thread4 = threading.Thread(target=infiniteloop4)
thread4.start()

thread5 = threading.Thread(target=infiniteloop5)
thread5.start()

thread6 = threading.Thread(target=infiniteloop6)
thread6.start()


sio = socketio.Client()

@sio.event
def connect():
    global serverConnCheck
    
    serverConnCheck = True
    print('Connected to server')

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
    #print(clientStates)
    #print("clientStates in message:", clientStates)

    if(json_data["msg"]=="Active" or json_data["msg"]=="Queue" or json_data["msg"]=="Song" or json_data["msg"]=="Backup"):
        #colorArrayBuilder(json_data["lights"])
        lights=json_data["lights"]
        lightCheck=True
        ringLightCheck = True

        print(bpmCountCheck)
        print(json_data["msg"])
        if(json_data["msg"]=="Song" and bpmCountCheck):
            print("playing song")
            playSong(["spotify:track:"+json_data["songdata"]["songID"]],json_data["songdata"]["timestamp"])
        
    elif(json_data["msg"]=="Seeking"):
        if playingCheck:
            print("Updating seek")
            currSeeker=sp.currently_playing()
            seekData=requests.post(baseUrl+"updateSeek", json={"seek":currSeeker['progress_ms'], "song":currSeeker['item']['id'],"prompt":"Bro"})
    elif(json_data["msg"]=="SeekSong"):
        if not playingCheck and bpmCountCheck:
            print("This is the new client")
            seekCheck=True
            seekedPlayer=json_data["songdata"]["timestamp"]
            playSong(["spotify:track:"+json_data["songdata"]["songID"]],json_data["songdata"]["timestamp"])

            lights=json_data["lights"]
            lightCheck=True
            ringLightCheck = True

    print("///////////////////////////////////////////////////////////////////////////////////////////////////////////")

sio.connect('https://qp-master-server.herokuapp.com/')
sio.wait()
    





