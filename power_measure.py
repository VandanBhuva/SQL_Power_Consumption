import os
import sys
import re
import glob
import csv
import statistics
import configparser
import tempfile
import shutil
import subprocess



def output_to_csv(config, cmd, i, temp_dir, id_mapping, runtimes):
    # list all csv files corresponding to each query
    csv_files = glob.glob(os.path.join(temp_dir, f"query_{i}*.csv"))
    power_data = []

    # search for power value corresponding to 'psql' in each csv
    for csv_file, runtime in zip(csv_files, runtimes):  # Zip runtimes with corresponding CSV files
        with open(csv_file, 'r') as f:
            pid_power = set()
            for line in f:
                line = line.strip()

                if re.search(r'(psql|postgres);', line, re.IGNORECASE):
                    pid_pattern = r'PID\s(\d*)'
                    power_pattern = r'(\d*\.?\d*)\s+(m|u)?W'
                    pid_match = re.search(pid_pattern, line)
                    power_match = re.search(power_pattern, line)

                    if power_match:
                        power_val = float(power_match.group(1))
                        power_unit = power_match.group(2)
                        if power_unit == 'u':
                            power_val *= pow(10, -6)
                        elif power_unit == 'm':
                            power_val *= pow(10, -3)

                        pid = int(pid_match.group(1))

                        pid_power.add((pid, power_val))

            final_power = sum(power for _, power in pid_power)

            power_data.append((id_mapping[cmd], cmd, round(final_power, 3), runtime))  # Append runtime to power data

    # append the (query, power) in a separate output file
    with open(config['files']['power_csv'], 'a', newline='') as output_file:
        csv_writer = csv.writer(output_file, quoting=csv.QUOTE_MINIMAL)

        # Write data
        for cmd_id, query, power, runtime in power_data:
            csv_writer.writerow([cmd_id, query, power, runtime])  # Include runtime in the row


def calculate_mean(config, id_mapping):
    # Read all the data from the power CSV file
    power_data = []
    with open(config['files']['power_csv'], 'r', newline='') as power_file:
        csv_reader = csv.reader(power_file)
        next(csv_reader)  # Skip header
        for row in csv_reader:
            power_data.append((int(row[0]), row[1], float(row[2]), float(row[3])))

    # Calculate mean power and runtime for each query
    query_mean = {}
    for cmd_id, query, power, runtime in power_data:
        if cmd_id in query_mean:
            query_mean[cmd_id].append((query, power, runtime))
        else:
            query_mean[cmd_id] = [(query, power, runtime)]

    # Calculate mean of power and runtime for each query
    mean_data = [(cmd_id, statistics.mean([power for _, power, _ in powers]), statistics.mean([runtime for _, _, runtime in powers])) for cmd_id, powers in query_mean.items()]

    # Write mean power and runtime to mean CSV file
    with open(config['files']['mean_file'], 'w', newline='') as mean_file:
        csv_writer = csv.writer(mean_file, quoting=csv.QUOTE_MINIMAL)
        # Write header
        csv_writer.writerow(["id", "query", "mean_power", "mean_runtime"])
        # Write data
        for cmd_id, mean_power, mean_runtime in mean_data:
            query = query_mean[cmd_id][0][0]  # Extracting the query corresponding to the ID
            csv_writer.writerow([cmd_id, query, mean_power, mean_runtime])

def extract_runtime(filename):
    runtimes = []
    with open(filename, 'r') as file:
        contents = file.read()
        # Use regular expression to find all occurrences of the runtime
        matches = re.findall(r"Time: (\d+\.\d+) ms", contents)
        if matches:
            for match in matches:
                runtime = float(match) / 1000  # Convert milliseconds to seconds
                runtimes.append(runtime)
    return runtimes
        
def run_powertop(config):
    # Set PostgreSQL password in the environment variable
    os.environ['PGPASSWORD'] = config['postgres']['password']

    # Create a temporary directory to store temporary CSV files
    temp_dir = tempfile.mkdtemp()

    id_mapping = {}  # To map queries to unique IDs
    next_id = 1

    try:
        with open(config['files']['queries_file'], 'r') as f:
            content = f.read()

            # make a list of commands to execute from the given command file
            commands = content.split(';')
            commands = [cmd.strip() for cmd in commands if cmd.strip()]

            for i, cmd in enumerate(commands):
                # Assign unique ID to the query
                if cmd not in id_mapping:
                    id_mapping[cmd] = next_id
                    next_id += 1

                # Write the query to a temporary file
                temp_query_file = os.path.join(temp_dir, f"query_{i}.sql")
                with open(temp_query_file, 'w') as temp_file:
                    temp_file.write(cmd)

                # psql command to supply as workload to powertop
                psql_cmd = f"PAGER=cat psql -h {config['postgres']['host']} -U {config['postgres']['user']} -d {config['postgres']['database']} -c '\\timing on' -f {temp_query_file} -c '\\timing off' >> temp_output_{i}.txt 2>&1"
                # final powertop command
                powertop_cmd = f"sudo -E powertop --quiet --workload=\"{psql_cmd}\" --csv={os.path.join(temp_dir, f'query_{i}.csv')} --iteration={config['powertop']['iterations']}"

                # print(f"\n\nRunning PowerTop for query : {cmd}.")
                os.system(powertop_cmd)

                # Extract runtime from temp_output.txt
                runtimes = extract_runtime(f'temp_output_{i}.txt')

                # Remove temporary file
                # Clean up temporary query file
                os.remove(temp_query_file)

                output_to_csv(config, cmd, i, temp_dir, id_mapping,runtimes)
                #os.remove('temp_output.txt')

    finally:

        # Remove temporary files
        for i in range(len(commands)):
            if os.path.exists(f'temp_output_{i}.txt'):
                os.remove(f'temp_output_{i}.txt')
        # Delete the temporary directory and its contents
        shutil.rmtree(temp_dir)

    # Calculate mean of power values
    calculate_mean(config, id_mapping)


def main():
    # Parse configuration from feature_config.ini file
    config = configparser.ConfigParser()
    config.read('feature_config.ini')

    # Clear the output CSV file
    with open(config['files']['power_csv'], 'w', newline='') as output_file:
        csv_writer = csv.writer(output_file, quoting=csv.QUOTE_MINIMAL)
        # Write header
        csv_writer.writerow(["id", "query", "power","runtime"])

    run_powertop(config)


if __name__ == "__main__":
    main()
