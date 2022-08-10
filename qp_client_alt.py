from threading import Timer
from time import time
import requests

#varibale to determine the user
userID=2
bpmAdded=170
# base_url1="https://qpmaster-server.herokuapp.com/"
# base_url2="https://qpone-server.herokuapp.com/"

base_url1="https://qpm-server.herokuapp.com/"
base_url2="https://qpt-server.herokuapp.com/"

playing=False
add=0
flag=0
bpmCheck=True
count=0
msFirst=0
msPrev=0
seekedPlayer=0

def makeUserActive():
    global userID
    userActive=requests.post(base_url1+"makeActive", json={"user_id":userID})
    print("Active Users :")
    print(userActive.json())
    # seekToPlay()

def seekToPlay():
    global seekedPlayer
    playerSeek=requests.get(base_url1+"getSeek")
    print(playerSeek.json())
    if(playerSeek.json()['seek']>0):
        trackArr=[]
        trackArr.append(playerSeek.json()['id'])
        playSong(trackArr)
        seekedPlayer=playerSeek.json()['seek']
        playSongFromSeek()

def pushBPMToPlay():
    print()
    print("Since Queue was Empty, Pushing song to Play")
    songToBePlayed=requests.post(base_url1+"getTrackToPlay", json={"bpm":bpmAdded, "userID":userID})
    print("Initial Queue : ", songToBePlayed.json())
    trackArr=[]
    trackArr.append("spotify:track:"+songToBePlayed.json()['song']['track_id'])
    playSong(trackArr)

def pushBPMToQueue(add):
    print()
    print("Since Song is playing, Pushing song to Queue")
    songToBeQueued=requests.post(base_url1+"getTrackToQueue", json={"bpm":bpmAdded, "userID":userID, "offset":add})
    print("Updated Queue : ",songToBeQueued.json())

def playSong(trkArr):
    print()
    print("Playing Song with ID: ", trkArr)
    song=requests.post(base_url2+"playback", json={"song":trkArr})
    global playing
    playing=True
    checkSongCompleted() 

def playSongsToContinue():
    print()
    print("Continue Playing")
    continueSong=requests.get(base_url1+"continuePlaying")

    trackArr=[]
    trackArr.append("spotify:track:"+continueSong.json()['song']['track_id'])
    global add
    add-=1
    playSong(trackArr)

    global playing
    playing=True
    checkSongCompleted() 

def playSongFromSeek():
    global seekedPlayer
    seekSong=requests.post(base_url2+"seek", json={"seek":seekedPlayer})
    checkSongCompleted()

def checkSongCompleted():
    global playing
    global seekedPlayer
    playerState=requests.get(base_url2+"getState")
    if playerState.json()['state']=="ended":
        playing=False
        playSongsToContinue()
    else:
        playing=True

    if playerState.json()['song'] != None: 
        playerSeek=requests.post(base_url1+"updateSeek", json={"song":"spotify:track:"+playerState.json()['song'],"seek":playerState.json()['seek']})

    if playing:
        Timer(1,checkSongCompleted).start()

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

def checkBPMAdded():    
    global playing, add, flag, bpmAdded
    msCurr=int(time()*1000)
    if flag==1 and msCurr-msPrev>1000*2:
        if playing:
            add+=1
            pushBPMToQueue(add)
        else:
            pushBPMToPlay()
        
        flag=0
    
    global bpmCheck
    if bpmCheck:
        Timer(1,checkBPMAdded).start()
        

makeUserActive()
checkBPMAdded()
print("Press enter for BPM")
while(1):
    value = input()
    if(value==""):
        TapBPM()