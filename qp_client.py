from threading import Timer
from time import time
import requests

userID=1
bpmAdded=170
base_url="http://localhost:8888/"
playing=False
add=0
flag=0
bpmCheck=True
count=0
msFirst=0
msPrev=0


def pushBPMToPlay():
    print("Playing")
    songToBePlayed=requests.post(base_url+"getTrackToPlay", json={"bpm":bpmAdded, "userID":userID})
    trackArr=[]
    trackArr.append("spotify:track:"+songToBePlayed.json()['song']['track_id'])
    playSong(trackArr)

def pushBPMToQueue(add):
    print("Updating Queue")
    songToBeQueued=requests.post(base_url+"getTrackToQueue", json={"bpm":bpmAdded, "userID":userID, "offset":add})
    print(songToBeQueued.json()['queue'])

def playSong(trkArr):
    song=requests.post(base_url+"playback", json={"song":trkArr})
    
    global playing
    playing=True
    checkSongCompleted() 

def playSongsToContinue():
    continueSong=requests.get(base_url+"continuePlaying")

    trackArr=[]
    trackArr.append("spotify:track:"+continueSong.json()['song']['track_id'])
    playSong(trackArr)

    global playing
    playing=True
    checkSongCompleted() 

def checkSongCompleted():
    global playing
    playerState=requests.get(base_url+"getState")
    if playerState.json()['state']=="ended":
        playing=False
        playSongsToContinue()
    else:
        playing=True

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
        print("BPM Requested")
        print(bpmAdded)
        if playing:
            add+=1
            pushBPMToQueue(add)
        else:
            pushBPMToPlay()
        
        flag=0
    
    global bpmCheck
    if bpmCheck:
        Timer(1,checkBPMAdded).start()
        

checkBPMAdded()
print("Press enter for BPM")
while(1):
    value = input()
    if(value==""):
        TapBPM()