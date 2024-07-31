# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Copyright 2024 Sam Blenny
#
# prox-sensor-encoder-menu
#
# Docs and Reference Code:
# - https://learn.adafruit.com/adafruit-i2c-qt-rotary-encoder/python-circuitpython
# - https://learn.adafruit.com/adafruit-vcnl4040-proximity-sensor
# - https://docs.circuitpython.org/projects/seesaw/en/latest/api.html
# - https://docs.circuitpython.org/projects/vcnl4040/en/latest/api.html
# - https://www.vishay.com/docs/84274/vcnl4040.pdf
#
from board import NEOPIXEL, NEOPIXEL_POWER, STEMMA_I2C
from digitalio import DigitalInOut, Direction
import gc
from neopixel_write import neopixel_write
from sys import stdout
from time import sleep

from adafruit_seesaw import digitalio
from adafruit_seesaw.seesaw import Seesaw
from adafruit_vcnl4040 import VCNL4040


class Encoder():
    # Wrapper for Seesaw I2C rotary encoder (Adafruit #5880 or #4991)
    def __init__(self, i2c, address):
        # Initialize encoder and verify Seesaw firmware version
        ssw = Seesaw(i2c, addr=0x36)
        ver = (ssw.get_version() >> 16) & 0xffff
        assert (ver == 4991), 'unexpected seesaw firmware version'
        # Enable pullup for knob-click button
        ssw.pin_mode(24, Seesaw.INPUT_PULLUP)
        self.ssw = ssw

    def clicked(self):
        # Return true when encoder knob button is pressed
        return not self.ssw.digital_read(24)

    def delta(self):
        # Return delta representing amount knob was turned
        return self.ssw.encoder_delta()


def showMenu(prefix, ctx):
    # Show the menu with selected item highlighted.
    # - ctx is the context dictionary
    #
    # Menu selection highlighting uses the ANSI escape code for
    # inverse video. To read more about that, see:
    #   https://en.wikipedia.org/wiki/ANSI_escape_code
    #
    # To update the menu selection in place, without needing to
    # start a new line each time, this uses a CR character ('\r')
    # to return the cursor to the left margin of the last line of
    # console output. But, there is also a check (newline) to avoid
    # stomping on the last line of console output from doAction().
    newline = ctx['newline']
    sel = ctx['selection']
    menu = ctx['menu']
    wr = stdout.write
    if newline:
        # Avoid stomping on console output from doAction()
        ctx['newline'] = False
        wr("\n")
    wr('\r%s: ' % prefix)     # CR moves cursor to left margin
    for (i, (name, _)) in enumerate(menu):
        if i == sel:
            wr(b'\x1b[7m')    # ANSI escape code for inverse text
            wr(' %s ' % name)
            wr(b'\x1b[0m')    # ANSI escape code for normal text
        else:
            wr(' %s ' % name)

def doAction(ctx):
    # Perform the action for the selected menu item
    print()  # showMenu ends without a '\n', so add one now
    selection = ctx['selection']
    (name, action) = ctx['menu'][selection]
    if not callable(action):
        # If this happens, check your context dictionary
        print(name, 'menu action is not callable')
    else:
        # Do action for selected menu
        action(ctx)
    # Tell showMenu to add a newline so it doesn't stomp on the
    # last line of output printed by action(context) above
    ctx['newline'] = True

def showProx(ctx):
    # Show current proximity sensor reading (click to stop)
    print("VCNL4040 Proximity (click to go back):")
    enc = ctx['enc']
    vcnl = ctx['vcnl']
    wr = stdout.write
    prevClick = False
    while True:
        sleep(0.1)  # poll at 10 Hz to reduce annoying flicker
        # Print current proximity measurement on same line as last one
        wr('\r proximity: % 6d  ' % vcnl.proximity)
        # End loop on edge trigger of knob pressed -> released
        click = enc.clicked()
        if (not click) and (click != prevClick):
            wr('\n')
            return
        prevClick = click
        # Update LED
        updateNeopixel(ctx)

def showLux(ctx):
    # Show current ambient illumination reading (click to stop)
    print("VCNL4040 Ambient Lux (click to go back):")
    enc = ctx['enc']
    vcnl = ctx['vcnl']
    wr = stdout.write
    prevClick = False
    while True:
        sleep(0.1)  # poll at 10 Hz to reduce annoying flicker
        # Print current lux measurement on same line as last one
        wr('\r lux: % 6d  ' % vcnl.lux)
        # End loop on edge trigger of knob pressed -> released
        click = enc.clicked()
        if (not click) and (click != prevClick):
            wr('\n')
            return
        prevClick = click
        # Update LED
        updateNeopixel(ctx)

def setThresh(ctx):
    # Set proximity threshold for changing Neopixel color
    # Proximity range of VCNL4040 is 200mm according to datasheet.
    # The proximity values seem to be log scale. Normal reading is
    # 1 with nothing in front of the sensor. It changes to 2 if
    # you put something reflective about 200mm away. Some very
    # approximate measurements for other values of .proximity:
    #  .proximity   mm
    #           2   150..200
    #           3   130..150
    #           4   110..130
    #           5   100..110
    #           6    90..100
    #           7    85..90
    #           8    80..85
    #          60    10
    print("Proximity threshold, range 2..60 (click to save):")
    enc = ctx['enc']
    LO = 2
    HI = 60
    wr = stdout.write
    prevClick = False
    thresh = ctx['threshold']
    while True:
        sleep(0.03)  # poll at 30 Hz so knob feels responsive
        # Print current threshold on same line as last one
        wr('\r threshold: % 6d  ' % thresh)
        click = enc.clicked()
        delta = enc.delta()
        # Handle knob click (edge trigger on pressed -> released)
        if (not click) and (click != prevClick):
            wr('\n')
            return
        prevClick = click
        # Handle knob turn
        if delta != 0:
            thresh = max(LO, min(HI, thresh + delta))
            ctx['threshold'] = thresh         # update context!
        # Update LED
        updateNeopixel(ctx)

def updateNeopixel(ctx):
    # Set neopixel according to thresholds and proximity sensor
    np = ctx['np']
    if ctx['vcnl'].proximity >= ctx['threshold']:
        neopixel_write(np, bytearray([5, 0, 5]))   # LED = cyan
    else:
        neopixel_write(np, bytearray([0, 0, 0]))   # LED = off

def select(delta, ctx):
    # Update menu selection by an increment of `delta` items.
    # Selection must be a valid index of context['menu'] array:
    # 1. max(0, ...) ensures 0 <= selection
    # 2. min(limit, ...) ensures selection < len(context['menu'])
    sel = ctx['selection']
    limit = len(ctx['menu']) - 1
    ctx['selection'] = max(0, min(limit, (sel + delta)))

def main():
    # Initialize hardware then start the event loop
    gc.collect()
    i2c = STEMMA_I2C()
    # Rotary Encoder
    enc = Encoder(i2c, 0x35)
    # Proximity and Lux sensor
    vcnl = VCNL4040(i2c)
    # Neopixel
    np = DigitalInOut(NEOPIXEL)
    pwr = DigitalInOut(NEOPIXEL_POWER)
    np.direction = Direction.OUTPUT
    pwr.direction = Direction.OUTPUT
    pwr.value = True

    # CONTEXT DICTIONARY AND NAV MENU
    #
    # The context dictionary holds shared data used by several
    # functions. You could use a class or individual variables for
    # this. But, for simple prototyping, a dictionary makes it easy
    # to try ideas quickly without typing lots of boilerplate code.
    # You can read about declaring dictionary literals at:
    #   https://docs.python.org/3/library/stdtypes.html#dict
    #
    # For the menu item list, each entry should be a tuple of
    # (name, callable object). The name gets used by the function
    # that prints the current menu selection. The callable object
    # gets used when you pick a menu item. In Python, functions and
    # methods are callable objects. You can call them with a `()`
    # after their name, or you can assign them to variables by
    # omitting the `()`.
    #
    ctx = {
        'menu': [             # Navigation menu
            ('Show Proxmity', showProx),
            ('Show Lux',      showLux),
            ('Set Threshold', setThresh),
        ],
        'enc': enc,           # Encoder object for submenus to use
        'vcnl': vcnl,         # VCNL4040 object for submenus to use
        'np': np,             # Neopixel pin (DigitalInOut)
        'newline': True,      # Should menu start on a new line?
        'selection': 0,       # Menu selection index
        'threshold': 4,       # Proximity threshold (range 2..60)
    }

    # EVENT LOOP
    prevClick = False
    while True:
        sleep(0.03)  # poll at 30 Hz so knob feels responsive
        # Update the menu every time through the loop, even if the
        # rotary encoder state has not changed. This makes it so,
        # if you connect to the USB serial port after code.py has
        # been running for a while, the menu shows up immediately.
        showMenu('Main', ctx)
        # Read the rotary encoder (Seesaw I2C)
        click = enc.clicked()
        delta = enc.delta()
        # Handle knob click (edge trigger on pressed -> released)
        if (not click) and (click != prevClick):
            doAction(ctx)
        prevClick = click
        # Handle knob turn
        if delta != 0:
            select(delta, ctx)
        # Update LED
        updateNeopixel(ctx)

main()
