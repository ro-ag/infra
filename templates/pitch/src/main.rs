//! pitch — convert between musical notes, frequencies, and MIDI note numbers.
//!
//! Zero dependencies, equal temperament, configurable A4 reference.
//!
//!   pitch A4          -> note to frequency
//!   pitch 442.3       -> frequency to nearest note + cents
//!   pitch --a4 432 A4 -> custom tuning reference

use std::process::ExitCode;

/// Semitone offsets from C for the seven natural notes.
const NATURALS: [(char, i32); 7] = [
    ('C', 0),
    ('D', 2),
    ('E', 4),
    ('F', 5),
    ('G', 7),
    ('A', 9),
    ('B', 11),
];
const SHARP_NAMES: [&str; 12] = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
];

/// Parse a note like `A4`, `C#4`, `Bb3`, `F-1` into a MIDI note number.
fn parse_note(s: &str) -> Option<i32> {
    let mut chars = s.chars();
    let letter = chars.next()?.to_ascii_uppercase();
    let mut semitone = NATURALS.iter().find(|(c, _)| *c == letter)?.1;

    let rest: String = chars.collect();
    let (accidental, octave_str) = match rest.chars().next() {
        Some('#') | Some('s') | Some('S') => (1, &rest[1..]),
        Some('b') | Some('B') | Some('f') => (-1, &rest[1..]),
        _ => (0, rest.as_str()),
    };
    semitone += accidental;

    let octave: i32 = octave_str.parse().ok()?;
    let midi = (octave + 1) * 12 + semitone;
    (0..=127).contains(&midi).then_some(midi)
}

/// MIDI note number to canonical (sharp) name, e.g. 70 -> "A#4".
fn note_name(midi: i32) -> String {
    format!("{}{}", SHARP_NAMES[(midi % 12) as usize], midi / 12 - 1)
}

/// Frequency in Hz for a MIDI note, given the A4 reference.
fn freq_of(midi: i32, a4: f64) -> f64 {
    a4 * 2f64.powf((midi - 69) as f64 / 12.0)
}

/// Nearest MIDI note and signed cents offset for a frequency.
fn note_of(freq: f64, a4: f64) -> (i32, f64) {
    let exact = 69.0 + 12.0 * (freq / a4).log2();
    let midi = exact.round().clamp(0.0, 127.0) as i32;
    (midi, (exact - f64::from(midi)) * 100.0)
}

fn usage() -> &'static str {
    "pitch — convert between musical notes and frequencies

USAGE:
    pitch [--a4 <hz>] <note>       note -> frequency   (e.g. pitch A4, pitch Bb3)
    pitch [--a4 <hz>] <frequency>  frequency -> note   (e.g. pitch 442.3)
    pitch --version
    pitch --help

OPTIONS:
    --a4 <hz>    A4 reference frequency (default: 440)"
}

fn run(query: &str, a4: f64) -> Result<String, String> {
    if let Ok(freq) = query.parse::<f64>() {
        if !(0.1..=20000.0).contains(&freq) {
            return Err(format!("frequency {freq} Hz out of range (0.1–20000)"));
        }
        let (midi, cents) = note_of(freq, a4);
        Ok(format!(
            "{freq:.2} Hz -> {} (MIDI {midi}), {cents:+.1} cents",
            note_name(midi)
        ))
    } else {
        let midi = parse_note(query)
            .ok_or_else(|| format!("'{query}' is neither a note (A4, C#3, Bb5) nor a frequency"))?;
        Ok(format!(
            "{} -> {:.2} Hz (MIDI {midi})",
            note_name(midi),
            freq_of(midi, a4)
        ))
    }
}

fn main() -> ExitCode {
    let mut a4 = 440.0;
    let mut query: Option<String> = None;
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--a4" => match args.next().and_then(|v| v.parse::<f64>().ok()) {
                Some(v) if (400.0..=480.0).contains(&v) => a4 = v,
                _ => {
                    eprintln!("error: --a4 needs a frequency between 400 and 480 Hz");
                    return ExitCode::FAILURE;
                }
            },
            "-h" | "--help" => {
                println!("{}", usage());
                return ExitCode::SUCCESS;
            }
            "--version" => {
                println!("pitch {}", env!("CARGO_PKG_VERSION"));
                return ExitCode::SUCCESS;
            }
            _ if query.is_none() => query = Some(arg),
            _ => {
                eprintln!("error: unexpected argument '{arg}'\n\n{}", usage());
                return ExitCode::FAILURE;
            }
        }
    }

    match query {
        Some(q) => match run(&q, a4) {
            Ok(line) => {
                println!("{line}");
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("error: {e}");
                ExitCode::FAILURE
            }
        },
        None => {
            eprintln!("{}", usage());
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_naturals() {
        assert_eq!(parse_note("A4"), Some(69));
        assert_eq!(parse_note("C4"), Some(60));
        assert_eq!(parse_note("G9"), Some(127));
        assert_eq!(parse_note("C-1"), Some(0));
    }

    #[test]
    fn parses_accidentals() {
        assert_eq!(parse_note("C#4"), Some(61));
        assert_eq!(parse_note("Bb3"), Some(58));
        assert_eq!(parse_note("Eb4"), Some(63));
        // enharmonic across octave boundary
        assert_eq!(parse_note("B#3"), Some(60));
        assert_eq!(parse_note("Cb4"), Some(59));
    }

    #[test]
    fn rejects_garbage() {
        assert_eq!(parse_note("H4"), None);
        assert_eq!(parse_note("A"), None);
        assert_eq!(parse_note("A10"), None); // above MIDI range
        assert_eq!(parse_note(""), None);
    }

    #[test]
    fn names_roundtrip() {
        for midi in 0..=127 {
            // sharps parse back to the same midi; flats tested above
            assert_eq!(parse_note(&note_name(midi)), Some(midi));
        }
    }

    #[test]
    fn a4_is_the_reference() {
        assert!((freq_of(69, 440.0) - 440.0).abs() < 1e-9);
        assert!((freq_of(69, 432.0) - 432.0).abs() < 1e-9);
        // middle C at A4=440
        assert!((freq_of(60, 440.0) - 261.626).abs() < 0.001);
        // one octave up doubles the frequency
        assert!((freq_of(81, 440.0) - 880.0).abs() < 1e-9);
    }

    #[test]
    fn frequencies_map_back() {
        let (midi, cents) = note_of(440.0, 440.0);
        assert_eq!(midi, 69);
        assert!(cents.abs() < 1e-9);

        // 445 Hz is sharp of A4 by ~19.6 cents
        let (midi, cents) = note_of(445.0, 440.0);
        assert_eq!(midi, 69);
        assert!((cents - 19.56).abs() < 0.01);
    }

    #[test]
    fn run_output() {
        assert_eq!(run("A4", 440.0).unwrap(), "A4 -> 440.00 Hz (MIDI 69)");
        assert_eq!(
            run("440", 440.0).unwrap(),
            "440.00 Hz -> A4 (MIDI 69), +0.0 cents"
        );
        assert!(run("H2", 440.0).is_err());
        assert!(run("0", 440.0).is_err());
    }
}
