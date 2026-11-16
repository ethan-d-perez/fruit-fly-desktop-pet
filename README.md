# fruit-fly-desktop-pet

## How to Run:
Download and run the .exe file. A fly should pop up on your desktop and in the bottom-right corner, there should be a
"FlyWire Manager" that let you control the number of flies and hide/show state information. You can minimize and maximize the
manager screen at any time. You can also close the manager to stop the program.

Flies will interact with one another by moving close to each other, wander around, flee from your cursor, and spin around to
escape if they are grabbed by your cursor (using a touchscreen is the easiest way to grab them).

## States:
Files currently have four states: Wandering, Socializing, Fleeing, and Struggling.

### Wandering:
This is the default or idle state of the finite state machine I built using the fly brain. In the WANDER state, this is
considered to be their "solo exploration" phase where they use PFL3 neurons pointed in front of them to send information to the 
excitatory DNa03 and inhibitory LAL010 interneurons into DNa02, which is responsible for steering. This results in clean, 
somewhat realistic pathing.

### Socializing:
Using LC10a neurons, other flies on the screen can respond to one another. The neurons give a slight pathing bias into DNa02 to 
influence their pathing and stay relatively close to each other. When a fly gets scared by the cursor and is in a group, it'll 
pass the warning to other flies and cause a mass scatter. This state is represented as SOCIAL in brain.py.

### Fleeing:
I kept this as FLEEING in the code, and this state is caused whenever the cursor nears a fly. When the cursor gets close to the 
fly, neurons LC4 and LPLC2 transmits information to DNp01 to make the fly move quickly and the opposite DNa02 hemisphere to make 
the fly shoot away from the cursor.

### Struggling:
I didn't use the FlyWire fly brain for this part of the project. Instead, I made the flies spin clockwise when grabbed because 
it's funny. It also beats them just being stiff and not doing anything at all.

## Why/How This Was Made:
I thought the Fruit Fly Brain Hack Day I co-hosted on behalf of Hack_NCState and Thinking Machines at NCSU on Saturday, November 
14 was a really fun prompt, and because there wasn't too much going on, I did this project as a way to keep myself occupied. 
This project was not judged because I was a host, and that would be very unfair to the participants. I did most of the 
improvements the day after, such as the manager, showing the different states, and comfortably adding multiple flies to the 
screen.

I made this using the back-up Colab journal we made for the event in case the first one didn't work for some reason. The Colab 
journal helped me export the brain data necessary to make this into .json files. The Colab journal is in the repo as a source, but it uses FlyWire and *fafbseg* to get the brain data necessary for the project. The source files were made in Python. 


*Full disclaimer: the idea was by me and original, but the code to make this happen was greatly assisted by generative AI. 
Fortunately, this entire summary was typed by me and based on the information I gathered to make this project. I do understand 
the majority of the code and process behind this project.*

*This code exists under a MIT license. Please feel free to innovate on this project if you feel so inclined for some reason, as long as credit is attributed somewhere.*
