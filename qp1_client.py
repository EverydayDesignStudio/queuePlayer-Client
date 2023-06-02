import threading
import keyboard
from pynput.keyboard import Key
from threading import Timer
from time import time
import requests
import websocket #import websockt library -> pip install websocket-client
import ssl # import ssl library (native)
import json # import json library (native)
import spotipy
from spotipy.oauth2 import SpotifyOAuth

#variable to determine the client number
clientID=1

#varibale to determine the client state
state=True

#variable that keeps the record of the current BPM added by the user
bpmAdded=36

#both hosted servers for queue player funcitonality
baseUrl="https://qp-master-server.herokuapp.com/"

playerID=""
playing=False
flag=0
bpmCheck=True
count=0
msFirst=0
msPrev=0
seekedPlayer=0
colorArrBefore=[(0,0,0,0)]*144
colorArrAfter=[0]*144

#Spotify Library Required Variables
#[OLO5 Credentials]
client_id='765cacd3b58f4f81a5a7b4efa4db02d2'
client_secret='cb0ddbd96ee64caaa3d0bf59777f6871'
spotify_username='n39su59fav4b7fmcm0cuwyv2w'
device_id='1632b74b504b297585776e716b8336510639401a'
spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing'
spotify_redirect_uri = 'http://localhost:8000'

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id, client_secret=client_secret, redirect_uri=spotify_redirect_uri, scope=spotify_scope, username=spotify_username, requests_session=True, requests_timeout=None, open_browser=True))

#function to show the states for each queue player client
def setClientActive():
    global clientID
    setClientActive=requests.post(baseUrl+"setClientActive", json={"clientID":clientID})
    print("Client States : \n")
    print(setClientActive.json())

#function to show the states for each queue player client
def setClientInactive():
    global clientID
    setClientInactive=requests.post(baseUrl+"setClientInactive", json={"clientID":clientID})
    print("Client States : \n")
    print(setClientInactive.json())

#function to push the BPM added by the client to the master server and use the spotify server to call and play the song if no song is in the queue
#simultaneously update the queue with the pushed BPM
def pushBPMToPlay():
    print("\nSince Queue was Empty, Pushing song to Play")
    songToBePlayed=requests.post(baseUrl+"getTrackToPlay", json={"bpm":bpmAdded, "clientID":clientID})

    # print("Initial Queue : \n")
    # for ele in songToBePlayed.json()['queue']:
    #     print(ele)

    trackArr=[]
    trackArr.append("spotify:track:"+songToBePlayed.json()['song']['track_id'])
    playSong(trackArr)

#function to push the BPM added by the client to the master server
#simultaneously update the queue with the pushed BPM as the player is playing
def pushBPMToQueue():
    print()
    print("Since Song is playing, Pushing song to Queue")
    songToBeQueued=requests.post(baseUrl+"getTrackToQueue", json={"bpm":bpmAdded, "userID":clientID})
    
    # print("Updated Queue : \n")
    # for ele in songToBeQueued.json()['queue']:
    #     print(ele)

#function to play the song by sending the request to the spotify server associated with this client
def playSong(trkArr):
    global playerID
    print(playerID)
    print()
    print("Playing Song with ID: ", trkArr)
    sp.start_playback(device_id=device_id, uris=trkArr)
    global playing
    playing=True

#function to continue playing immediately
def playSongsToContinue():
    global playing
    continueSongImmediate=requests.get(baseUrl+"continuePlayingImmediate")
    trackArr=[]
    trackArr.append("spotify:track:"+continueSongImmediate.json()['song']['track_id'])
    playSong(trackArr)
    playing=True

#function to get the current timestamp playing in all the rest of the players and seek the player 
def seekToPlay():
    global seekedPlayer
    playerSeek=requests.get(baseUrl+"getSeek")
    if(playerSeek.json()['seek']>0):
        print("Seeked Song")
        print(playerSeek)
        trackArr=[]
        trackArr.append("spotify:track:"+playerSeek.json()['id'])
        playSong(trackArr)
        seekedPlayer=playerSeek.json()['seek']
        playSongFromSeek()

#function to play the song pointed with the seek timestamp by sending the request to the spotify server associated with this client
def playSongFromSeek():
    global seekedPlayer, device_id
    print("PlayFromSeek: ", seekedPlayer)
    sp.seek_track(seekedPlayer, device_id)

#function to calculate BPM input
def TapBPM(): 
    global count
    global msFirst  
    global msPrev
    global flag

    msCurr=int(time()*1000)
    if(msCurr-msPrev > 1000*2):
        count = 0

    if(count == 0):
        msFirst = msCurr
        count = 1
    else:
        bpmAvg= 60000 * count / (msCurr-msFirst)
        global bpmAdded
        bpmAdded=round(round(bpmAvg*100)/100)
        count+=1 

    msPrev=msCurr
    flag=1

#function to periodically check the client state to indicate when a bpm is added
def checkBPMAdded():    
    global playing,flag, bpmAdded
    msCurr=int(time()*1000)
    if flag==1 and msCurr-msPrev>1000*2:
        if playing:
            pushBPMToQueue()
        else:
            pushBPMToPlay()
        
        flag=0
    
    global bpmCheck
    global bpmTimer
    if bpmCheck:
        bpmTimer=Timer(2,checkBPMAdded)
        bpmTimer.start()
    else:
        bpmTimer.cancel()

def colorArrayBuilder(lights):
    global colorArrBefore,colorArrAfter
    n=0
    for ring in lights:
        colors=lights[ring]["colors"]
        print(len(colors))
        divs=int(36/len(colors))
        for i in colors:
            colorArrAfter[n:n+divs]=[(colors[i]["r"],colors[i]["g"],colors[i]["b"],colors[i]["w"])] * divs
            n=n+divs

    print(colorArrAfter[0:36])
    print(colorArrAfter[36:72])
    print(colorArrAfter[72:108])
    print(colorArrAfter[108:144])

setClientActive()
seekToPlay()
checkBPMAdded()

print("Press enter for BPM")

def infiniteloop1():
    while True:
        value = input()
        if(value==""):
            TapBPM()
        # time.sleep(1)

def infiniteloop2():
    while True:
        if playing:
            if sp.currently_playing()['progress_ms']>0 and sp.currently_playing()['item']['id'] != None:
                seekData=requests.post(baseUrl+"updateSeek", json={"seek":sp.currently_playing()['progress_ms'], "song":sp.currently_playing()['item']['id']})
            if sp.currently_playing()['progress_ms']>10000:
                if(sp.currently_playing()['progress_ms']+10000>=sp.currently_playing()['item']['duration_ms']):
                    print("Song has ended")
                    playSongsToContinue()

def infiniteloop3():
    while True:
        # websocket.enableTrace(True) # print the connection details (for debuggi>
        ws = websocket.WebSocketApp("wss://qp-master-server.herokuapp.com/", # websocket URL to connect
            on_message = on_message, # what should happen when we receive a new message
            on_error = on_error, # what should happen when we get an error
            on_close = on_close, # what should happen when the connection is closed
            on_ping = on_ping, # on ping
            on_pong = on_pong) # on pong
        ws.on_open = on_open # call on_open function when the ws connection is opened
        # ws.run_forever(reconnect=5, ping_interval=15, ping_timeout=10, ping_payload="This is an optional ping payload", sslopt={"cert_reqs": ssl.CERT_NONE}) # run code forever and disable the requirement of SSL certificates
        ws.run_forever(reconnect=1, sslopt={"cert_reqs": ssl.CERT_NONE}) # run code forever and disable the requirement of SSL certificates


def on_message(ws, message): # function which is called whenever a new message comes in
    json_data = json.loads(message) # incoming message is transformed into a JSON object
    print("")
    print("Server Sent the JSON:")
    print(json.dumps(json_data, indent = 2))
    colorArrayBuilder(json_data["lights"])
    global playing
    if playing:
        print("playing")
    else:
        seekToPlay()
    print("") # printing new line for better legibility

def on_error(ws, error): # function call when there is an error
    print(error)

def on_close(ws): # function call when the connection is closed (this should not happend currently as we are staying connected)
    print("### closed ###")

def on_open(ws): # function call when a new connection is established
    print("### open ###")

def on_ping(wsapp, message):
    print("Got a ping! A pong reply has already been automatically sent. ", message)

def on_pong(wsapp, message):
    print("Got a pong! No need to respond. ", message)

    
thread1 = threading.Thread(target=infiniteloop1)
thread1.start()

thread2 = threading.Thread(target=infiniteloop2)
thread2.start()

thread3 = threading.Thread(target=infiniteloop3)
thread3.start()

while state:
    if keyboard.is_pressed("o"):
        bpmCheck=False
        setClientInactive()
        sp.pause_playback(device_id=device_id)
        print("Client is set Inactive")
    elif keyboard.is_pressed("s"):
        bpmCheck=True
        setClientActive()
        seekToPlay()
        checkBPMAdded()
        print("Client is set Active")




