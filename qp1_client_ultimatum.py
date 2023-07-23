import keyboard
from pynput.keyboard import Key
import copy
import threading
from threading import Timer
import time
import requests
import socketio
import json 
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException


# import board
# import neopixel
# import RPi.GPIO as GPIO
# import busio
# import adafruit_ads1x15.ads1015 as ADS
# from adafruit_ads1x15.analog_in import AnalogIn

# #Setup for potentiometer and piezo ADC channels 
# i2c = busio.I2C(board.SCL, board.SDA)
# ads = ADS.ADS1015(i2c)
# chan_piezo = AnalogIn(ads, ADS.P0)  #piezo connected to pin A0 
# chan_pot = AnalogIn(ads, ADS.P1) #potentiometer connected to pin A1

# #Variables to tune and adjust piezo sensitivity 
# THRESHOLD = 0.8  # Adjust this value based on your piezo sensitivity
# DEBOUNCE_TIME = 0.1  # Adjust this value based on min. time needed between consecutive taps

# #Neopixel Setup for strip and ring light 
# pixel_pin1 = board.D12 # the pin to which the LED strip is connected to
# pixel_pin2 = board.D10 # the pin to which the ring light is connected to
# num_pixels = 144 # this specifies the TOTAL number of pixels (should be a multiple of 12. ie. 12, 24, 36, 48 etc)
# num_ring_pixels = 16
# ORDER = neopixel.GRBW # set the color type of the neopixel
# ledSegment = 36 # number of LEDs in a single segment
# ledArray = [[[0 for i in range(4)] for j in range(ledSegment)] for z in range(4)] #the array which stores the pixel information

# # #Create and initiate neopixel objects
# pixels = neopixel.NeoPixel(pixel_pin1, num_pixels, brightness=0.2, auto_write=False, pixel_order=ORDER)
# ring_pixels = neopixel.NeoPixel(pixel_pin2, num_ring_pixels, brightness = 0.4, auto_write = False, pixel_order=ORDER)



#Client essential variables
clientID=1
    #[OLO5 : QP Client Credentials]
client_id='765cacd3b58f4f81a5a7b4efa4db02d2'
client_secret='cb0ddbd96ee64caaa3d0bf59777f6871'
spotify_username='n39su59fav4b7fmcm0cuwyv2w'
device_id='1632b74b504b297585776e716b8336510639401a'
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
    global colorArrBefore,colorArrAfter

    n=0
    for ring in lights:
        colors=lights[ring]["colors"]
        divs=int(36/len(colors))
        rgb_vals=[]
        for i in colors:
            rgb_vals.append((colors[i]["r"],colors[i]["g"],colors[i]["b"],colors[i]["w"]))
        for i in range(len(rgb_vals)):
            colorArrAfter[n:n+divs]=interpolate_rgbw(rgb_vals[i],rgb_vals[(i+1)%len(rgb_vals)], divs)
            n=n+divs
   
#    #Check if color array is different to trigger fade in and out
#     if colorArrBefore != colorArrAfter:
#         # Define the maximum brightness value
#         max_brightness = 255 

#         # Fade-out effect
#         for brightness in range(max_brightness, -1, -1):
#             for i in range (144):
#                 pixels[i] = colorArrBefore[i]
#             #pixels.fill(colorArrBefore)
#             pixels.brightness = brightness / max_brightness
#             pixels.show()
#             time.sleep(0.01)  # Adjust the delay time as desired

#         # Fade-in effect
#         for brightness in range(max_brightness + 1):
#             for i in range (144):
#                 pixels[i] = colorArrAfter[i]
#             #pixels.fill(colorArrAfter)
#             pixels.brightness = brightness / max_brightness
#             pixels.show()
#             time.sleep(0.01)  # Adjust the delay time as desired
    
#         colorArrBefore = copy.deepcopy(colorArrAfter)

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

def infiniteloop1():
    while True:
        value = input()
        if(value==""):
            TapBPM()

    # while True:
    #     global THRESHOLD, DEBOUNCE_TIME
    #
    #     if chan_piezo.voltage >= THRESHOLD * ads.gain:
    #         current_time = time.monotonic()  # Get the current time
            
    #         # Apply debounce: Ignore taps that occur within the debounce time window
    #         if current_time - last_tap_time > DEBOUNCE_TIME:
    #             last_tap_time = current_time  # Update the last tap time
    #             print("Tap detected")
    #             TapBPM()
    #     time.sleep(0.01)  # Adjust the sleep time based on your requirements

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
                    currVolume = sp.current_playback()['device']['volume_percent']
                    currVolume=currVolume*0.95
                    sp.volume(int(currVolume), device_id)   
                
                if totalTime-elapsed_time<=2000:
                    print("Song has ended")
                    seekedPlayer=0
                    playSongsToContinue(currDuration,currSongID, "Normal")          
        else:
            rx=1

def infiniteloop3():
    global bpmCountCheck,prevVal,currVol,playingCheck, currSongID, seekedClient, durationCheck

    while True:
        if keyboard.is_pressed("o"):
        # if chan_pot.voltage < 0.01:
            if playingCheck and bpmCountCheck:
                playingCheck=False
                bpmCountCheck=False
                sp.pause_playback(device_id=device_id) # will givw the error for spotify command failed have to incorporate similar mechanism as volume
                setClientInactive()
                seekData=requests.post(baseUrl+"updateSeek", json={"seek":seekedClient+seekedPlayer, "song":currSongID,"prompt":"Continue"})
                print("Client is set Inactive")

        elif keyboard.is_pressed("s"):
        # elif chan_pot.voltage > 1.0 and not bpmCountCheck:
            bpmCountCheck=True
            setClientActive()
            checkBPMAdded()
            print("Client is set Active")
            print("Press enter for BPM")

        # if bpmCountCheck and playingCheck:
        #     currVol = int (map_to_volume(chan_pot.voltage))
        #     #print(currVol)
        #     if(abs(prevVal-currVol) >= 5):
        #         sp.volume(currVol, device_id)
        #         prevVal = currVol
        #         print("changing volume")


thread1 = threading.Thread(target=infiniteloop1)
thread1.start()

thread2 = threading.Thread(target=infiniteloop2)
thread2.start()

thread3 = threading.Thread(target=infiniteloop3)
thread3.start()


sio = socketio.Client()

@sio.event
def connect():
    print('Connected to server')

@sio.event
def disconnect():
    print('Disconnected from server')

@sio.event
def message(data):
    global playingCheck, currSongID,seekCheck,seekedPlayer

    json_data = json.loads(data) # incoming message is transformed into a JSON object
    print("Server Sent the JSON:")
    print(json.dumps(json_data, indent = 2))
    if(json_data["msg"]=="Active" or json_data["msg"]=="Queue" or json_data["msg"]=="Song" or json_data["msg"]=="Backup"):
        colorArrayBuilder(json_data["lights"])
        if(json_data["msg"]=="Song" and bpmCountCheck):
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

    print("///////////////////////////////////////////////////////////////////////////////////////////////////////////")

sio.connect('https://qp-master-server.herokuapp.com/')
sio.wait()
    





