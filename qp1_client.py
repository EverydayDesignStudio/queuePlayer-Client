import threading
from threading import Timer
from time import time
import requests
import websocket #import websockt library -> pip install websocket-client
import ssl # import ssl library (native)
import json # import json library (native)
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyPKCE
import spotipy.util as util

#variable to determine the client number
clientID=1

#variable that keeps the record of the current BPM added by the user
bpmAdded=36

#both hosted servers for queue player funcitonality
baseUrl="https://qp-master-server.herokuapp.com/"

playerID=""
playing=False
add=0
flag=0
bpmCheck=True
count=0
msFirst=0
msPrev=0
seekedPlayer=0
timeouter=0

#Spotify Library Required Variables
#[OLO5 Credentials]
client_id='765cacd3b58f4f81a5a7b4efa4db02d2'
client_secret='cb0ddbd96ee64caaa3d0bf59777f6871'
spotify_username='n39su59fav4b7fmcm0cuwyv2w'
device_id='1632b74b504b297585776e716b8336510639401a'
spotify_scope='user-library-read,user-modify-playback-state,user-read-currently-playing'
spotify_redirect_uri = 'https://example.com/callback/'

token = util.prompt_for_user_token(spotify_username, spotify_scope, client_id = client_id, client_secret = client_secret, redirect_uri = spotify_redirect_uri)
if token:
    sp = spotipy.Spotify(auth=token)

#function to show the states for each queue player client
def toggleClientActive():
    global clientID
    toggleClientActive=requests.post(baseUrl+"toggleClientActive", json={"clientID":clientID})
    print("Client States : \n")
    print(toggleClientActive.json())

#function to push the BPM added by the client to the master server and use the spotify server to call and play the song if no song is in the queue
#simultaneously update the queue with the pushed BPM
def pushBPMToPlay():
    print("\nSince Queue was Empty, Pushing song to Play")
    songToBePlayed=requests.post(baseUrl+"getTrackToPlay", json={"bpm":bpmAdded, "clientID":clientID})

    print("Initial Queue : \n")
    for ele in songToBePlayed.json()['queue']:
        print(ele)

    trackArr=[]
    trackArr.append("spotify:track:"+songToBePlayed.json()['song']['track_id'])
    playSong(trackArr)

#function to push the BPM added by the client to the master server
#simultaneously update the queue with the pushed BPM as the player is playing
def pushBPMToQueue(add):
    print()
    print("Since Song is playing, Pushing song to Queue")
    songToBeQueued=requests.post(baseUrl+"getTrackToQueue", json={"bpm":bpmAdded, "userID":clientID, "offset":add})
    # print("Updated Queue : ",songToBeQueued.json())

#function to play the song by sending the request to the spotify server associated with this client
def playSong(trkArr):
    global playerID
    print(playerID)
    print()
    print("Playing Song with ID: ", trkArr)
    sp.start_playback(device_id=device_id, uris=trkArr)
    global playing
    playing=True

#function to continue playing the next song from the queue by sending the request to the spotify server associated with this client
# def playSongsToContinue():
#     print()
#     global add,playing, timeouter
#     tc=Timer(1,playSongsToContinue)
#     timeouter+=1
#     print("Continue Playing")
#     print("Timeout Timer: ", timeouter)
#     if(timeouter>=10):
#         continueSongImmediate=requests.get(baseUrl+"continuePlayingImmediate")
#         trackArr=[]
#         trackArr.append("spotify:track:"+continueSongImmediate.json()['song']['track_id'])
#         add-=1
#         playSong(trackArr)
#         playing=True

#     continueSong=requests.post(baseUrl+"continuePlaying", json={"user_id":userID})
#     if(timeouter<10 and len(continueSong.json()['queue']) != 0):
#         trackArr=[]
#         trackArr.append("spotify:track:"+continueSong.json()['song']['track_id'])
#         add-=1
#         playSong(trackArr)

#         playing=True

#     if playing:
#         tc.cancel()
#         timeouter=0

#function to continue playing immediately
def playSongsToContinue():
    global add, playing
    continueSongImmediate=requests.get(baseUrl+"continuePlayingImmediate")
    trackArr=[]
    trackArr.append("spotify:track:"+continueSongImmediate.json()['song']['track_id'])
    add-=1
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
    global playing, add, flag, bpmAdded
    msCurr=int(time()*1000)
    if flag==1 and msCurr-msPrev>1000*2:
    # if flag==1:
        if playing:
            add+=1
            pushBPMToQueue(add)
        else:
            pushBPMToPlay()
        
        flag=0
    
    global bpmCheck
    if bpmCheck:
        Timer(2,checkBPMAdded).start()

toggleClientActive()
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
        # websocket.enableTrace(True) # print the connection details (for debugging purposes)
        ws = websocket.WebSocketApp("wss://qp-master-server.herokuapp.com/", # websocket URL to connect to
                                on_message = on_message, # what should happen when we receive a new message
                                on_error = on_error, # what should happen when we get an error
                                on_close = on_close) # what should happen when the connection is closed
        ws.on_open = on_open # call on_open function when the ws connection is opened
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}) # run code forever and disable the requirement of SSL certificates

def on_message(ws, message): # function which is called whenever a new message comes in
    json_data = json.loads(message) # incoming message is transformed into a JSON object
    print("")
    print("Server Sent the JSON:")
    print(message) # printing the data (for testing purposes)
    # print(json_data["blockHash"]) # printing a specific part of the JSON object (for testing purposes)
    print("") # printing new line for better legibility

def on_error(ws, error): # function call when there is an error
    print(error)

def on_close(ws): # function call when the connection is closed (this should not happend currently as we are staying connected)
    print("### closed ###")

def on_open(ws): # function call when a new connection is established
    print("### open ###")

def infiniteloop3():
    while True:
        if playing:
            if sp.currently_playing()['progress_ms']>0 and sp.currently_playing()['item']['id'] != None:
                seekData=requests.post(baseUrl+"updateSeek", json={"seek":sp.currently_playing()['progress_ms'], "song":sp.currently_playing()['item']['id']})
            if sp.currently_playing()['progress_ms']>10000:
                if(sp.currently_playing()['progress_ms']+10000>=sp.currently_playing()['item']['duration_ms']):
                    print("Song has ended")
                    playSongsToContinue()

    
thread1 = threading.Thread(target=infiniteloop1)
thread1.start()

thread2 = threading.Thread(target=infiniteloop2)
thread2.start()

thread3 = threading.Thread(target=infiniteloop3)
thread3.start()


