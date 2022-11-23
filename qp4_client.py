import threading
from threading import Timer
from time import time
import requests
import websocket #import websockt library -> pip install websocket-client
import ssl # import ssl library (native)
import json # import json library (native)

#variable to determine the user
userID=4

#variable that keeps the record of the current BPM added by the user
bpmAdded=36

#both hosted servers for queue player funcitonality
base_url1="https://qpm-server.herokuapp.com/"
base_url2="https://qp4-spotify-server.herokuapp.com/"

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



#function to check the active users for each queue player client
def makeUserActive():
    global userID
    userActive=requests.post(base_url1+"makeActive", json={"user_id":userID})
    print("Active Users :")
    print(userActive.json())

#function to get the available devices linked to the authenticated account and get their player id for playback
def availableDevice():
    ad=requests.get(base_url2+'getAvailable')
    print("Available devices :")
    print(ad.json())
    global playerID
    playerID=ad.json()[0]['id']

#function to get the current timestamp playing in all the rest of the players and seek the player 
def seekToPlay():
    global seekedPlayer
    playerSeek=requests.get(base_url1+"getSeek")
    if(playerSeek.json()['seek']>0):
        print("Seeked Song")
        print(playerSeek)
        trackArr=[]
        trackArr.append("spotify:track:"+playerSeek.json()['id'])
        playSong(trackArr)
        seekedPlayer=playerSeek.json()['seek']
        playSongFromSeek()

#function to push the BPM added by the client to the master server and use the spotify server to call and play the song if no song is in the queue
#simultaneously update the queue with the pushed BPM
def pushBPMToPlay():
    print()
    print("Since Queue was Empty, Pushing song to Play")
    songToBePlayed=requests.post(base_url1+"getTrackToPlay", json={"bpm":bpmAdded, "userID":userID})
    print("Initial Queue : ", songToBePlayed.json())
    trackArr=[]
    trackArr.append("spotify:track:"+songToBePlayed.json()['song']['track_id'])
    playSong(trackArr)

#function to push the BPM added by the client to the master server
#simultaneously update the queue with the pushed BPM as the player is playing
def pushBPMToQueue(add):
    print()
    print("Since Song is playing, Pushing song to Queue")
    songToBeQueued=requests.post(base_url1+"getTrackToQueue", json={"bpm":bpmAdded, "userID":userID, "offset":add})
    print("Updated Queue : ",songToBeQueued.json())

#function to play the song by sending the request to the spotify server associated with this client
def playSong(trkArr):
    global playerID
    print(playerID)
    print()
    print("Playing Song with ID: ", trkArr)
    song=requests.post(base_url2+"playback", json={"song":trkArr, "player":playerID})
    print(song)
    global playing
    playing=True
    # checkSongCompleted() 

#function to continue playing the next song from the queue by sending the request to the spotify server associated with this client
def playSongsToContinue():
    print()
    global add,playing, timeouter
    tc=Timer(1,playSongsToContinue)
    timeouter+=1
    print("Continue Playing")
    print("Timeout Timer: ", timeouter)
    if(timeouter>=10):
        continueSongImmediate=requests.get(base_url1+"continuePlayingImmediate")
        trackArr=[]
        trackArr.append("spotify:track:"+continueSongImmediate.json()['song']['track_id'])
        add-=1
        playSong(trackArr)

        playing=True


    continueSong=requests.post(base_url1+"continuePlaying", json={"user_id":userID})
    if(timeouter<10 and len(continueSong.json()['queue']) != 0):
        trackArr=[]
        trackArr.append("spotify:track:"+continueSong.json()['song']['track_id'])
        add-=1
        playSong(trackArr)

        playing=True

    if playing:
        tc.cancel()
        timeouter=0


#function to play the song pointed with the seek timestamp by sending the request to the spotify server associated with this client
def playSongFromSeek():
    global seekedPlayer
    print("PlayFromSeek: ", seekedPlayer)
    seekSong=requests.post(base_url2+"seek", json={"seek":seekedPlayer})

#function to periodically check the player state to indicate when a song is finished
def checkSongCompleted():
    global playing
    global seekedPlayer
    tt=Timer(1,checkSongCompleted)

    playerState=requests.get(base_url2+"getState")
    if playing and playerState.json()['state']=="ended":
        print("Song has ended")
        playing=False
        playSongsToContinue()
    else:
        playing=True

    if playerState.json()['song'] != None: 
        playerSeek=requests.post(base_url1+"updateSeek", json={"song":playerState.json()['song'],"seek":playerState.json()['seek']})

    if playing:
        tt.start()
    else:
        tt.cancel()

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

makeUserActive()
availableDevice()
seekToPlay()
checkBPMAdded()

print("Press enter for BPM")
# while(1):
#     value = input()
#     if(value==""):
#         TapBPM()

def infiniteloop1():
    while True:
        playerState=requests.get(base_url2+"getState")
        seekData=requests.post(base_url1+"updateSeek", json={"seek":playerState.json()['seek'], "song":playerState.json()['song']})
        if playerState.json()['state']=="ended":
            print("Song has ended")
            playSongsToContinue()
        # time.sleep(1)

def infiniteloop2():
    while True:
        value = input()
        if(value==""):
            TapBPM()
        # time.sleep(1)

def infiniteloop3():
    while True:
        websocket.enableTrace(True) # print the connection details (for debugging purposes)
        ws = websocket.WebSocketApp("wss://qpm-server.herokuapp.com/", # websocket URL to connect to
                                on_message = on_message, # what should happen when we receive a new message
                                on_error = on_error, # what should happen when we get an error
                                on_close = on_close) # what should happen when the connection is closed
        ws.on_open = on_open # call on_open function when the ws connection is opened
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}) # run code forever and disable the requirement of SSL certificates

def on_message(ws, message): # function which is called whenever a new message comes in
    json_data = json.loads(message) # incoming message is transformed into a JSON object
    print(message) # printing the data (for testing purposes)
    # print(json_data["blockHash"]) # printing a specific part of the JSON object (for testing purposes)
    print("") # printing new line for better legibility

def on_error(ws, error): # function call when there is an error
    print(error)

def on_close(ws): # function call when the connection is closed (this should not happend currently as we are staying connected)
    print("### closed ###")

def on_open(ws): # function call when a new connection is established
    print("### open ###")

    
thread1 = threading.Thread(target=infiniteloop1)
thread1.start()

thread2 = threading.Thread(target=infiniteloop2)
thread2.start()

thread3 = threading.Thread(target=infiniteloop3)
thread3.start()


