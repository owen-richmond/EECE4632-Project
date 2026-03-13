"""
midi_utils.py - MIDI message helpers for FPGA Musician
Owen Richmond, EECE4632

Just the 3-byte MIDI format: [status, note, velocity]
"""
#sample notes thanks CHATGPT
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
NOTE_ALIASES = {'Db': 'C#', 'Eb': 'D#', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#'}


def note_to_midi(note_str):
    # parse something like "A4" or "C#5"
    note_str = note_str.strip()
    if len(note_str) >= 3 and note_str[1] in ('#', 'b'):
        name, octave = note_str[:2], int(note_str[2:])
    else:
        name, octave = note_str[0], int(note_str[1:])
    name = NOTE_ALIASES.get(name, name)
    return (octave + 1) * 12 + NOTE_NAMES.index(name)


def midi_to_freq(note):
    # standard equal temperament, A4=440Hz
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def midi_to_name(note):
    return f"{NOTE_NAMES[note % 12]}{(note // 12) - 1}"

#hardcoding TS cuz its easier to read than hex
def note_on(note, velocity=100, channel=0):
    return bytes([0x90 | (channel & 0x0F), note & 0x7F, velocity & 0x7F])


def note_off(note, channel=0):
    return bytes([0x80 | (channel & 0x0F), note & 0x7F, 0x00])


def make_sequence(notes):
    # notes = list of (note_str, duration_sec, velocity)
    events = []
    t = 0.0
    for note_str, dur, vel in notes:
        midi = note_to_midi(note_str) if isinstance(note_str, str) else note_str
        msg = note_on(midi, vel)
        events.append({
            'time_on': t,
            'time_off': t + dur,
            'midi_on': msg,
            'note': midi,
            'note_name': midi_to_name(midi),
            'freq': round(midi_to_freq(midi), 3),
            'velocity': vel,
        })
        t += dur
    return events


def pack_axi(msg):
    # pack 3-byte MIDI into one 32-bit register for AXI-Lite writes
    return (msg[0] << 16) | (msg[1] << 8) | msg[2]

# convert a MIDI sequence to a raw audio waveform for testing purposes..
if __name__ == '__main__':
    scale = [('C4',0.4,80),('D4',0.4,80),('E4',0.4,80),('F4',0.4,80),
             ('G4',0.4,90),('A4',0.4,90),('B4',0.4,90),('C5',0.4,100)]
    events = make_sequence(scale)
    for ev in events:
        msg = ev['midi_on']
        print(f"t={ev['time_on']:.2f}s  {ev['note_name']:4s}  {ev['freq']:7.2f} Hz"
              f"  vel={ev['velocity']}  bytes={msg.hex(' ').upper()}"
              f"  axi=0x{pack_axi(msg):08X}")
