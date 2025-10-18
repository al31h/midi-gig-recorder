import rtmidi
import time
import sys
from threading import Lock

# --- Configuration ---
MIDI_PORT_1_KEYWORD = "Standard MIDI"  # Change to a unique part of your standard MIDI device name
MIDI_PORT_2_KEYWORD = "CQ18T"          # Change to a unique part of your CQ18T MIDI device name
# ---------------------

# MIDI Note Names for conversion
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Lock for thread-safe printing/logging
print_lock = Lock()

def get_note_name(note_number):
    """Converts a MIDI note number (0-127) to a note name (e.g., C3)."""
    if 0 <= note_number <= 127:
        octave = (note_number // 12) - 1
        note = NOTE_NAMES[note_number % 12]
        return f"{note}{octave}"
    return "???"

def parse_midi_message_1(message, time_stamp):
    """Parses and formats standard MIDI messages from the first interface."""
    midi_data = message[0]
    # Status byte is the first byte of the MIDI message
    status = midi_data[0]
    
    # Extract channel (0-15) - status bytes 0x80 to 0xE0 are channel messages
    channel = (status & 0x0F) + 1
    
    # Message type (High 4 bits of the status byte)
    msg_type = status & 0xF0

    output_line = None
    
    # Timecode formatting (seconds elapsed since port was opened)
    timecode = f"{time_stamp:.4f}"

    if 0x80 <= msg_type <= 0x90 and len(midi_data) >= 3:
        # Note Off (0x80) or Note On (0x90)
        note_number = midi_data[1]
        velocity = midi_data[2]
        note_name = get_note_name(note_number)
        
        if msg_type == 0x80 or (msg_type == 0x90 and velocity == 0):
            # 0x80 is Note Off. 0x90 with velocity 0 is also Note Off.
            output_line = f"{timecode} Note Off {note_name} <{velocity}>"
        elif msg_type == 0x90:
            output_line = f"{timecode} Note On {note_name} <{velocity}>"

    elif msg_type == 0xB0 and len(midi_data) >= 3:
        # Control Change (CC)
        cc_number = midi_data[1]
        value = midi_data[2]
        # Check for standard Start/Stop/Continue System Real Time messages
        if cc_number == 0x79: # Unassigned (most likely a CC)
             output_line = f"{timecode} CC {cc_number} <{value}>"
        else:
             output_line = f"{timecode} CC {cc_number} <{value}>"


    elif msg_type == 0xC0 and len(midi_data) >= 2:
        # Program Change (PC)
        pc_value = midi_data[1]
        output_line = f"{timecode} PC <{pc_value}>"

    elif msg_type == 0xE0 and len(midi_data) >= 3:
        # Pitch Bend Change
        lsb = midi_data[1]
        msb = midi_data[2]
        pitch_value = (msb << 7) | lsb
        # Range is 0 to 16383. Center is 8192.
        output_line = f"{timecode} Pitch Bend <{pitch_value}>"
        
    elif status == 0xF0:
        # System Exclusive (Sysex) - Starts with 0xF0 and ends with 0xF7
        hex_data = ' '.join(f'{b:02X}' for b in midi_data)
        output_line = f"{timecode} Sysex {hex_data}"
        
    elif status == 0xFA:
        output_line = f"{timecode} Start"
    elif status == 0xFB:
        output_line = f"{timecode} Continue"
    elif status == 0xFC:
        output_line = f"{timecode} Stop"
    elif status == 0xF8:
        # MIDI Clock - often filtered, but if not, log it quietly
        pass # output_line = f"{timecode} Clock" 
    elif status == 0xFE:
        # Active Sensing - often filtered, but if not, log it quietly
        pass # output_line = f"{timecode} Active Sensing"
    
    # Fallback for unparsed messages
    if output_line is None:
        hex_data = ' '.join(f'{b:02X}' for b in midi_data)
        output_line = f"{timecode} Unknown MIDI Message: {hex_data}"

    with print_lock:
        print(f"[IFACE 1] {output_line}")

def parse_midi_message_2(message, time_stamp):
    """
    Parses and formats custom CQ18T NRPN messages from the second interface.
    
    The CQ18T messages are essentially multiple Control Change messages grouped
    together, forming an NRPN sequence (CC99/CC98 for parameter address, CC6/CC38 for value).
    
    - 9 bytes (Mute Toggle): B0 63 <ch_msb> B0 62 <ch_lsb> B0 60 00
    - 12 bytes (Mute On/Off): B0 63 <ch_msb> B0 62 <ch_lsb> B0 06 00 B0 26 <on/off>
    - 12 bytes (Level): B0 63 <ch_msb> B0 62 <ch_lsb> B0 06 <val_msb> B0 26 <val_lsb>
    """
    midi_data = message[0]
    length = len(midi_data)
    output_line = None
    timecode = f"{time_stamp:.4f}"
    
    # Function to get channel number from MSB/LSB (example: 0x00 0x00 could be Chan 1)
    # The actual mapping of MSB/LSB to a specific channel/parameter is complex (NRPN address).
    # We will log the MSB/LSB for clarity, as the exact channel map isn't provided.
    
    try:
        if length == 9:
            # Expected pattern: B0 63 MSB B0 62 LSB B0 60 00
            if (midi_data[0] == 0xB0 and midi_data[1] == 0x63 and 
                midi_data[3] == 0xB0 and midi_data[4] == 0x62 and 
                midi_data[6] == 0xB0 and midi_data[7] == 0x60 and midi_data[8] == 0x00):
                
                ch_msb = midi_data[2]
                ch_lsb = midi_data[5]
                output_line = (f"{timecode} CQ18T Mute Toggle "
                               f"Address (CC99/98): {ch_msb:02X}/{ch_lsb:02X}")

        elif length == 12:
            # Expected pattern: B0 63 MSB B0 62 LSB B0 06 D_MSB B0 26 D_LSB
            if (midi_data[0] == 0xB0 and midi_data[1] == 0x63 and 
                midi_data[3] == 0xB0 and midi_data[4] == 0x62 and 
                midi_data[6] == 0xB0 and 
                midi_data[8] == 0xB0 and midi_data[9] == 0x26):
                
                ch_msb = midi_data[2]
                ch_lsb = midi_data[5]
                data_msb = midi_data[7]
                data_lsb = midi_data[10]
                
                # Mute On/Off
                if data_msb == 0x00:
                    if data_lsb == 0x01:
                        output_line = (f"{timecode} CQ18T Mute On "
                                       f"Address (CC99/98): {ch_msb:02X}/{ch_lsb:02X}")
                    elif data_lsb == 0x00:
                        output_line = (f"{timecode} CQ18T Mute Off "
                                       f"Address (CC99/98): {ch_msb:02X}/{ch_lsb:02X}")
                    else:
                        # Fallback for unexpected 12-byte with D_MSB=00
                        pass
                
                # Level/Fader
                else:
                    # Value is 14-bit: (data_msb * 128) + data_lsb
                    level_value = (data_msb << 7) | data_lsb
                    output_line = (f"{timecode} CQ18T Level (NRPN Data) <{level_value}> "
                                   f"Address (CC99/98): {ch_msb:02X}/{ch_lsb:02X} "
                                   f"Raw Value (CC6/38): {data_msb:02X}/{data_lsb:02X}")

        # Fallback for unparsed messages
        if output_line is None:
            hex_data = ' '.join(f'{b:02X}' for b in midi_data)
            output_line = f"{timecode} CQ18T Unrecognized ({length} bytes): {hex_data}"
    
    except IndexError:
        # Catches messages shorter than expected if they partially match a condition
        hex_data = ' '.join(f'{b:02X}' for b in midi_data)
        output_line = f"{timecode} CQ18T Incomplete/Bad Message: {hex_data}"
    
    with print_lock:
        print(f"[IFACE 2] {output_line}")


def select_port(midiin, keyword):
    """Allows user to select a port based on a keyword."""
    ports = midiin.get_ports()
    if not ports:
        print("No MIDI input ports found.")
        return None

    print(f"\nAvailable MIDI input ports (Search Keyword: '{keyword}'):")
    
    # Try to auto-select
    selected_port = -1
    for i, port in enumerate(ports):
        print(f"  [{i}] {port}")
        if keyword.lower() in port.lower():
            selected_port = i
    
    if selected_port != -1:
        print(f"Auto-selected port [{selected_port}] for '{keyword}'.")
        return selected_port
    
    print(f"\nCould not auto-select port for '{keyword}'. Please enter the number manually:")
    
    while True:
        try:
            choice = input(f"Select port number for '{keyword}': ")
            port_index = int(choice)
            if 0 <= port_index < len(ports):
                return port_index
            else:
                print("Invalid number. Please try again.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def main():
    """Main function to initialize and run the MIDI recorder."""
    midiin = rtmidi.MidiIn()
    
    # --- Port 1 Setup (Standard MIDI) ---
    port_1_index = select_port(midiin, MIDI_PORT_1_KEYWORD)
    if port_1_index is None:
        sys.exit(1)

    port_1_name = midiin.get_port_name(port_1_index)
    midi_in_1 = rtmidi.MidiIn()
    midi_in_1.open_port(port_1_index)
    
    # Enable Sysex, Clock, and Active Sensing for comprehensive logging
    midi_in_1.ignore_types(False, False, False)
    midi_in_1.set_callback(parse_midi_message_1)
    
    print(f"\n[OK] Opened Interface 1: {port_1_name}. Recording standard MIDI traffic.")

    # --- Port 2 Setup (CQ18T) ---
    port_2_index = select_port(midiin, MIDI_PORT_2_KEYWORD)
    if port_2_index is None:
        sys.exit(1)
        
    port_2_name = midiin.get_port_name(port_2_index)
    # Note: A new MidiIn instance is required for a separate port
    midi_in_2 = rtmidi.MidiIn() 
    midi_in_2.open_port(port_2_index)
    
    # We ignore standard Real-Time messages on this port too, but enable Sysex
    midi_in_2.ignore_types(False, False, False)
    midi_in_2.set_callback(parse_midi_message_2)
    
    print(f"[OK] Opened Interface 2: {port_2_name}. Recording CQ18T custom messages.")
    
    print("\n--- MIDI Recording Started (Press Ctrl+C to stop) ---")

    try:
        # Keep the script running to receive messages via the callback function
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n--- Recording Stopped ---")
    finally:
        # Clean up
        midi_in_1.close_port()
        midi_in_2.close_port()
        del midi_in_1
        del midi_in_2
        del midiin

if __name__ == '__main__':
    main()
