import argparse
import os
import re
import sys
import ast
from shutil import copy2

def parse_env(env_path):
    """Parse .env file for required configuration."""
    config = {}
    with open(env_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith('LOCAL_TRANSCRIPT_OUTPUT_DIR'):
            config['LOCAL_TRANSCRIPT_OUTPUT_DIR'] = line.split('=', 1)[1].strip().strip('"')
        elif line.startswith('DESTINATIONS_LEVEL_1'):
            # Read dict block
            dict_lines = [line.split('=', 1)[1].strip()]
            j = i + 1
            while not dict_lines[-1].endswith('}'):
                dict_lines.append(lines[j].strip())
                j += 1
            config['DESTINATIONS_LEVEL_1'] = ast.literal_eval(''.join(dict_lines))
        elif line.startswith('DESTINATIONS_LEVEL_2'):
            dict_lines = [line.split('=', 1)[1].strip()]
            j = i + 1
            while not dict_lines[-1].endswith('}'):
                dict_lines.append(lines[j].strip())
                j += 1
            config['DESTINATIONS_LEVEL_2'] = ast.literal_eval(''.join(dict_lines))
    return config

def is_dash_separated_filename(line):
    """Check if a line is a dash-separated filename (not a link)."""
    return (
        '-' in line and
        not line.startswith('https://') and
        re.fullmatch(r'[a-zA-Z0-9\-]+', line)
    )

def parse_input(input_path):
    """Extract all valid filenames from the input file."""
    filenames = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if is_dash_separated_filename(line):
                filenames.append(line)
    return filenames

def parse_filename(filename, level1_dict, level2_dict):
    """Break down filename into subject, class type, and date using dicts."""
    # Try to match the longest level1 key at the start
    level1_key = None
    for k in sorted(level1_dict.keys(), key=lambda x: -len(x)):
        if filename.startswith(k + '-'):
            level1_key = k
            break
    if not level1_key:
        return None, None, None, 'Subject not found'
    rest = filename[len(level1_key)+1:]
    # Next, match level2 key
    level2_key = None
    for k in level2_dict.keys():
        if rest.startswith(k + '-'):
            level2_key = k
            break
    if not level2_key:
        return None, None, None, 'Class type not found'
    date_part = rest[len(level2_key)+1:]
    # Validate date: DD-MM-YY (allow single-digit D/M)
    if not re.fullmatch(r'\d{1,2}-\d{1,2}-\d{2}', date_part):
        return None, None, None, 'Invalid date format'
    return level1_key, level2_key, date_part, None

def build_destination(level1_key, level2_key, date_part, level1_dict, level2_dict):
    """Build the destination directory path."""
    level1_dir = level1_dict[level1_key]
    level2_dir = level2_dict[level2_key]
    return os.path.join(level1_dir, level2_dir, date_part)

def main():
    parser = argparse.ArgumentParser(description="Distribute transcript files into structured folders.")
    parser.add_argument('input_file', type=str, help='Path to the input file listing transcript filenames.')
    parser.add_argument('--dry-run', action='store_true', help='Show plan only, do not copy files.')
    parser.add_argument('--log-file', type=str, help='Write full log and summary to this file.')
    parser.add_argument('--env', type=str, default='.env', help='Path to .env file.')
    args = parser.parse_args()

    log_lines = []
    def log(msg):
        print(msg)
        log_lines.append(msg)

    # Parse config
    try:
        config = parse_env(args.env)
        level1_dict = config['DESTINATIONS_LEVEL_1']
        level2_dict = config['DESTINATIONS_LEVEL_2']
        transcript_dir = config['LOCAL_TRANSCRIPT_OUTPUT_DIR']
    except Exception as e:
        log(f'[FATAL] Failed to parse .env: {e}')
        sys.exit(1)

    # Parse input
    filenames = parse_input(args.input_file)
    log(f'[INFO] Found {len(filenames)} candidate filenames in {args.input_file}')

    # Plan
    plan = []
    errors = []
    for fname in filenames:
        level1_key, level2_key, date_part, err = parse_filename(fname, level1_dict, level2_dict)
        if err:
            errors.append((fname, err))
            continue
        src_txt = os.path.join(transcript_dir, fname + '.txt')
        dest_dir = build_destination(level1_key, level2_key, date_part, level1_dict, level2_dict)
        dest_txt = os.path.join(dest_dir, fname + '.txt')
        dest_tex = os.path.join(dest_dir, fname + '.tex')
        # Check source file
        if not os.path.isfile(src_txt):
            errors.append((fname, 'Source transcript file missing'))
            continue
        # Check destination files
        if os.path.exists(dest_txt) or os.path.exists(dest_tex):
            errors.append((fname, 'Destination .txt or .tex file already exists'))
            continue
        plan.append({
            'filename': fname,
            'src_txt': src_txt,
            'dest_dir': dest_dir,
            'dest_txt': dest_txt,
            'dest_tex': dest_tex
        })

    # Present plan
    log('\n[PLAN] The following files will be copied:')
    for item in plan:
        log(f"  {item['filename']}: {item['src_txt']} -> {item['dest_txt']} (and empty .tex)")
    if not plan:
        log('[PLAN] No files to copy.')
    if errors:
        log('\n[SKIPPED] The following files will be skipped due to errors:')
        for fname, reason in errors:
            log(f'  {fname}: {reason}')
    else:
        log('\n[SKIPPED] No files skipped.')

    if args.dry_run:
        log('\n[DRY-RUN] No files will be copied.')
        if args.log_file:
            with open(args.log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(log_lines))
        return

    # Prompt for confirmation
    proceed = input('\nProceed with copying files? (y/N): ').strip().lower()
    if proceed != 'y':
        log('[ABORTED] No files were copied.')
        if args.log_file:
            with open(args.log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(log_lines))
        return

    # Execute plan
    successes = []
    for item in plan:
        try:
            os.makedirs(item['dest_dir'], exist_ok=True)
            copy2(item['src_txt'], item['dest_txt'])
            with open(item['dest_tex'], 'w', encoding='utf-8') as f:
                pass
            log(f"[OK] {item['filename']} copied to {item['dest_txt']} and empty .tex created.")
            successes.append(item['filename'])
        except Exception as e:
            errors.append((item['filename'], f'I/O error: {e}'))

    # Final summary
    log('\n[SUMMARY]')
    log(f'  Successfully copied: {len(successes)}')
    for fname in successes:
        log(f'    {fname}')
    log(f'  Skipped (errors): {len(errors)}')
    for fname, reason in errors:
        log(f'    {fname}: {reason}')

    if args.log_file:
        with open(args.log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_lines))

if __name__ == '__main__':
    main()