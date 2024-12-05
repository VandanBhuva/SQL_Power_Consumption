import argparse
import os
import sys
import re
import glob
import csv
import statistics



def output_to_csv(args, cmd, i):

    # list all csv files corresponding to each query
    csv_files = glob.glob(f"./query_{i}*.csv")
    power_data = []

    # search for power value corresponding to 'psql' in each csv
    for csv_file in csv_files:
        with open(csv_file, 'r') as f:
            pid_power = set()
            for line in f:
                line = line.strip()

                if re.search(r'psql;', line, re.IGNORECASE):
                    pid_pattern = r'PID\s(\d*)'
                    power_pattern = r'(\d*\.?\d*)\s+[m|u]W'
                    pid_match = re.search(pid_pattern, line)
                    power_match = re.search(power_pattern, line)

                    power_val = float(power_match.group(1))
                    power_unit = power_match.group(0)[-2]
                    if power_unit == 'u':
                        power_val *= pow(10,-3)

                    pid = int(pid_match.group(1))

                    pid_power.add((pid, power_val))
            
            final_power = 0
            for pid, power in pid_power:
                final_power += power      

            power_data.append((cmd, round(final_power,3)))
        # os.remove(csv_file)

    # append the (query, power) in a separate output file
    with open(args.output, 'a', newline='') as output_file:
        csv_writer = csv.writer(output_file, quoting=csv.QUOTE_MINIMAL)

        for cmd, power in power_data:
            # power_output = f"{power}"
            csv_writer.writerow([cmd, power])
        
        output_file.close()


def run_powertop(args):
    os.environ['PGPASSFILE'] = f"{args.passwd}"
    
    with open(args.command_file, 'r') as f:
        content = f.read()

        # make a list of commands to execute from the given command file
        commands = content.split(';')
        commands = [cmd.strip() for cmd in commands if cmd.strip()]
        
        for i, cmd in enumerate(commands):
            # psql command to supply as workload to powertop
            psql_cmd = f"psql -h {args.hostname} -U {args.username} -d {args.database} -c \\\"{cmd}\\\""
            # final powertop command
            powertop_cmd = f"sudo -E powertop --workload=\"{psql_cmd}\" --csv=query_{i}.csv --iteration={args.iterations}"
            
            print(f"\n\nRunning PowerTop for query : {cmd}.")
            os.system(powertop_cmd)

            output_to_csv(args, cmd, i)

    


def main():
    parser = argparse.ArgumentParser(description="Powertop to CSV")

    # Define flags
    parser.add_argument("-H", "--hostname", help="Hostname of the server")
    parser.add_argument("-U", "--username", help="Username for database connection")
    parser.add_argument("-d", "--database", help="Database name")
    parser.add_argument("-i", "--iterations", type=int, help="Number of iterations")
    parser.add_argument("-f", "--command_file", help="File containing SQL commands")
    parser.add_argument("-p", "--passwd", help="Path of your .pgpass file")
    parser.add_argument("-o", "--output", help="Output csv filename")

    args = parser.parse_args()
  
    run_powertop(args)

    

if __name__ == "__main__":
    main()
