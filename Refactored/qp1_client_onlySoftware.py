import keyboard
from pynput.keyboard import Key
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
import signal
import sys

#Identity variable of Client
clientID=1

#Global variable for Spotify
sp=None
device_id=None

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
someRelevantOutputCheck = True


clientStates = []

#BPM function variables
bpmAdded=215
tapCount=0
msFirst=0
msPrev=0

#Server Variable
baseUrl="https://qp-master-server.herokuapp.com/"

#Global volume variables 
prevVol = 0 #previous value for volume
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
    try:
        sp.start_playback(device_id=device_id, uris=trkArr, position_ms=pos)
    except:
        print("Minor Setback, Continue Continue")
    sp.volume(currVol, device_id)   
    playingCheck=True
    durationCheck=True


def playSongsToContinue(songDuration, songID, msg): 
    global playingCheck,prevDuration, prevID
    playingCheck=False
    prevDuration=songDuration
    prevID=songID
    continueSong=requests.get(baseUrl+"continuePlaying", json={"userID":clientID,"msg":msg})

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
            bpmAvg= 60000 * tapCount / (msCurr-msFirst)
            bpmAdded=round(round(bpmAvg*100)/100)
        # bpmAdded=137
        tapCount+=1 

    msPrev=msCurr
    bpmTapCheck=True

#function to periodically check the client state to indicate when a bpm is added
def checkBPMAdded():    
    global playingCheck, bpmTapCheck, bpmAdded, bpmCountCheck, bpmTimer

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
    global bpmCountCheck,prevVol,currVol,playingCheck, currSongID, seekedClient, durationCheck
    try:
        while True:
            if keyboard.is_pressed("s"):
            #if chan_pot.voltage > 0.1 and not bpmCountCheck and serverConnCheck:
                #currVol = int (map_to_volume(chan_pot.voltage)) #set current volume to potentiometer value
                sio.connect('https://qp-master-server.herokuapp.com/')
                bpmCountCheck=True
                checkBPMAdded()

                setClientActive()
                print("Client is set Active")
                print("Press enter for BPM")
            
            elif keyboard.is_pressed("o") and playingCheck and bpmCountCheck:
            #if chan_pot.voltage < 0.04:
                    playingCheck=False
                    bpmCountCheck=False
                    sp.pause_playback(device_id=device_id) # will give the error for spotify command failed have to incorporate similar mechanism as volume
                    setClientInactive()
                    print("Client is set Inactive")
                    seekData=requests.post(baseUrl+"updateSeek", json={"seek":seekedClient+seekedPlayer, "song":currSongID,"prompt":"Continue"})
                    sio.disconnect()

                    #pixels.fill((0,0,0,0))
                    #pixels.show()
                    # fadeToBlack()

            if bpmCountCheck and playingCheck:
                #currVol = int (map_to_volume(chan_pot.voltage)) 
                #print(currVol)
                if(abs(prevVol-currVol) >= 5):
                    try:
                        sp.volume(currVol, device_id)
                    except:
                        print("Minor Setback, Continue Continue")
                    prevVol = currVol
                    print("changing volume")
    except KeyboardInterrupt:
        # Cleanup code to be executed before termination
        print("\nCleaning up before exit...")


def infiniteloop2():
    try:
        while True:
            if bpmCountCheck:
                print("tap the bpm")
                value = input()
                if(value==""):
                    TapBPM()
    except KeyboardInterrupt:
    # Cleanup code to be executed before termination
        print("\nCleaning up before exit...")


def infiniteloop3():
    global prevDuration, prevID, startTime ,totalTime, durationCheck, currSongID, seekCheck, seekedPlayer,seekedClient, currDuration, playback
    try:
        while True:
            if playingCheck:    
                if(durationCheck):
                    print("Duration Checking")
                    try:
                        currSongItem = sp.currently_playing()['item']
                    except requests.exceptions.ReadTimeout:
                        print("Minor Setback, Continue Continue")

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
                            print("Minor Setback, Continue Continue")
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
    # Cleanup code to be executed before termination
        print("\nCleaning up before exit...")



sio = socketio.Client()
@sio.event
def connect():
    global serverConnCheck, device_id, sp
    serverConnCheck = True
    print('Connected to server')
    sio.emit('connect_user',{"userID":1})

    #[OLO5 Credentials]
    #Client essential variables
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
    global playingCheck, currSongID,seekCheck,seekedPlayer,lights,lightCheck, ringLightCheck, clientStates, someRelevantOutputCheck

    json_data = json.loads(data) # incoming message is transformed into a JSON object
    print("Server Sent the JSON:")
    print(json.dumps(json_data, indent = 2))

    # someRelevantOutputCheck=True
    # while someRelevantOutputCheck:

    if(json_data["msg"]!="Initial"):
        clientStates = json_data["activeUsers"]
        someRelevantOutputCheck=False
    #print(clientStates)
    #print("clientStates in message:", clientStates)

    if(json_data["msg"]=="Active" or json_data["msg"]=="Queue" or json_data["msg"]=="Song" or json_data["msg"]=="Backup"):
        #colorArrayBuilder(json_data["lights"])
        lights=json_data["lights"]
        lightCheck=True
        ringLightCheck = True

        someRelevantOutputCheck=False

        if(json_data["msg"]=="Song" and bpmCountCheck):
            print("Playing song")
            playSong(["spotify:track:"+json_data["songdata"]["songID"]],json_data["songdata"]["timestamp"])
            someRelevantOutputCheck=False

    elif(json_data["msg"]=="Seeking"):
        if playingCheck:
            print("Updating seek")
            try:
                currSeeker=sp.currently_playing()
            except requests.exceptions.ReadTimeout:
                print("Minor Setback, Continue Continue")

            seekData=requests.post(baseUrl+"updateSeek", json={"seek":currSeeker['progress_ms'], "song":currSeeker['item']['id'],"prompt":"Bro"})
            someRelevantOutputCheck=False

    elif(json_data["msg"]=="SeekSong"):
        if not playingCheck and bpmCountCheck:
            print("This is the new client")
            seekCheck=True
            seekedPlayer=json_data["songdata"]["timestamp"]
            playSong(["spotify:track:"+json_data["songdata"]["songID"]],json_data["songdata"]["timestamp"])

            lights=json_data["lights"]
            lightCheck=True
            ringLightCheck = True

            someRelevantOutputCheck=False






thread1 = threading.Thread(target=infiniteloop1)
thread1.start()

thread2 = threading.Thread(target=infiniteloop2)
thread2.start()

thread3 = threading.Thread(target=infiniteloop3)
thread3.start()

sio.wait()

