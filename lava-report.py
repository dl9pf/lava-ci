#!/usr/bin/python
# <variable> = required
# Usage ./lava-report.py <option> [json]
import argparse
import time
import subprocess
import re
import urllib2
import requests
from utils import *

log2html = 'https://git.linaro.org/people/kevin.hilman/build-scripts.git/blob_plain/HEAD:/log2html.py'

device_map = {'armada-370-mirabox': ['armada-370-mirabox', 'mvebu'],
              'arndale': ['exynos5250-arndale', 'exynos'],
              'snow': ['exynos5250-snow', 'exynos'],
              'arndale-octa': ['exynos5420-arndale-octa','exynos'],
              'peach-pi': ['exynos5800-peach-pi', 'exynos'],
              'odroid-xu3': ['exynos5422-odroidxu3', 'exynos'],
              'odroid-u2': ['exynos4412-odroidu3', 'exynos'],
              'odroid-x2': ['exynos4412-odroidx2', 'exynos'],
              'beaglebone-black': ['am335x-boneblack', 'omap2'],
              'beagle-xm': ['omap3-beagle-xm', 'omap2'],
              'panda-es': ['omap4-panda-es', 'omap2'],
              'panda': ['omap4-panda', 'omap2'],
              'cubieboard3': ['sun7i-a20-cubietruck', 'sunxi'],
              'cubieboard3-kvm-host': ['sun7i-a20-cubietruck-kvm-host', 'sunxi'],
              'cubieboard3-kvm-guest': ['sun7i-a20-cubietruck-kvm-guest', 'sunxi'],
              'optimus-a80': ['sun9i-a80-optimus', 'sunxi'],
              'cubieboard4': ['sun9i-a80-cubieboard4', 'sunxi'],
              'hi3716cv200': ['hisi-x5hd2-dkb', 'hisi'],
              'd01': ['hip04-d01', 'hisi'],
              'imx6q-wandboard': ['imx6q-wandboard', 'imx'],
              'imx6q-sabrelite': ['imx6q-sabrelite', 'imx'],
              'utilite-pro': ['imx6q-cm-fx6', 'imx'],
              'snowball': ['ste-snowball', 'u8500'],
              'ifc6540': ['qcom-apq8084-ifc6540', 'qcom'],
              'ifc6410': ['qcom-apq8064-ifc6410','qcom'],
              'sama53d': ['at91-sama5d3_xplained', 'at91'],
              'jetson-tk1': ['tegra124-jetson-tk1', 'tegra'],
              'parallella': ['zynq-parallella', 'zynq'],
              'qemu-arm-cortex-a15': ['vexpress-v2p-ca15-tc1', 'vexpress'],
              'qemu-arm-cortex-a15-a7': ['vexpress-v2p-ca15_a7', 'vexpress'],
              'qemu-arm-cortex-a9': ['vexpress-v2p-ca9', 'vexpress'],
              'qemu-arm': ['versatilepb', 'versatile'],
              'qemu-aarch64': ['qemu-aarch64', 'qemu'],
              'mustang': ['apm-mustang', 'apm'],
              'mustang-kvm-host': ['apm-mustang-kvm-host', 'apm'],
              'mustang-kvm-guest': ['apm-mustang-kvm-guest', 'apm'],
              'juno': ['juno', 'arm'],
              'juno-kvm-host': ['juno-kvm-host', 'arm'],
              'juno-kvm-guest': ['juno-kvm-guest', 'arm'],
              'minnowboard-max-E3825': ['minnowboard-max', None],
              'x86': ['x86', None],
              'kvm': ['x86-kvm', None]}


def download_log2html(url):
    print 'Fetching latest log2html script'
    response = urllib2.urlopen(url)
    script = response.read()
    write_file(script, 'log2html.py', os.getcwd())

def parse_json(json):
    jobs = load_json(json)
    url = validate_input(jobs['username'], jobs['token'], jobs['server'])
    connection = connect(url)
    duration = jobs['duration']
    # Remove unused data
    jobs.pop('duration')
    jobs.pop('username')
    jobs.pop('token')
    jobs.pop('server')
    return connection, jobs, duration


def boot_report(args):
    connection, jobs, duration =  parse_json(args.boot)
    # TODO: Fix this when multi-lab sync is working
    #download_log2html(log2html)
    results_directory = os.getcwd() + '/results'
    results = {}
    dt_tests = False
    mkdir(results_directory)
    for job_id in jobs:
        print 'Job ID: %s' % job_id
        # Init
        boot_meta = {}
        api_url = None
        arch = None
        board_instance = None
        boot_retries = 0
        kernel_defconfig_full = None
        kernel_defconfig = None
        kernel_defconfig_base = None
        kernel_version = None
        device_tree = None
        kernel_endian = None
        kernel_tree = None
        kernel_image = None
        kernel_addr = None
        initrd_addr = None
        dtb_addr = None
        dtb_append = None
        fastboot = None
        fastboot_cmd = None
        test_plan = None
        job_file = ''
        dt_test = None
        dt_test_result = None
        dt_tests_passed = None
        dt_tests_failed = None
        board_offline = False
        kernel_boot_time = None
        boot_failure_reason = None
        # Retrieve job details
        job_details = connection.scheduler.job_details(job_id)
        if job_details['requested_device_type_id']:
            device_type = job_details['requested_device_type_id']
        if job_details['description']:
            job_name = job_details['description']
        result = jobs[job_id]['result']
        bundle = jobs[job_id]['bundle']
        if bundle is None and device_type == 'dynamic-vm':
            host_job_id = job_id.replace('.1', '.0')
            bundle = jobs[host_job_id]['bundle']
            if bundle is None:
                print '%s bundle is empty, skipping...' % device_type
                continue
        # Retrieve the log file
        try:
            binary_job_file = connection.scheduler.job_output(job_id)
        except xmlrpclib.Fault:
            print 'Job output not found for %s' % device_type
            continue
        # Parse LAVA messages out of log
        raw_job_file = str(binary_job_file)
        for line in raw_job_file.splitlines():
            if 'Infrastructure Error:' in line:
                print 'Infrastructure Error detected!'
                index = line.find('Infrastructure Error:')
                boot_failure_reason = line[index:]
                board_offline = True
            if 'Bootloader Error:' in line:
                print 'Bootloader Error detected!'
                index = line.find('Bootloader Error:')
                boot_failure_reason = line[index:]
                board_offline = True
            if 'Kernel Error:' in line:
                print 'Kernel Error detected!'
                index = line.find('Kernel Error:')
                boot_failure_reason = line[index:]
            if 'Userspace Error:' in line:
                print 'Userspace Error detected!'
                index = line.find('Userspace Error:')
                boot_failure_reason = line[index:]
            if '<LAVA_DISPATCHER>' not in line:
                if len(line) != 0:
                    job_file += line + '\n'
            if '### dt-test ### end of selftest' in line:
                dt_tests = True
                regex = re.compile("(?P<test>\d+\*?)")
                dt_test_results = regex.findall(line)
                if len(dt_test_results) > 2:
                    dt_tests_passed = dt_test_results[2]
                    dt_tests_failed = dt_test_results[3]
                else:
                    dt_tests_passed = dt_test_results[0]
                    dt_tests_failed = dt_test_results[1]
                if int(dt_tests_failed) > 0:
                    dt_test_result = 'FAIL'
                else:
                    dt_test_result = 'PASS'
        # Retrieve bundle
        if bundle is not None:
            json_bundle = connection.dashboard.get(bundle)
            bundle_data = json.loads(json_bundle['content'])
            # Get the boot data from LAVA
            for test_results in bundle_data['test_runs']:
                # Check for the LAVA self boot test
                if test_results['test_id'] == 'lava':
                    for test in test_results['test_results']:
                        # TODO for compat :(
                        if test['test_case_id'] == 'kernel_boot_time':
                            kernel_boot_time = test['measurement']
                        if test['test_case_id'] == 'test_kernel_boot_time':
                            kernel_boot_time = test['measurement']
                    bundle_attributes = bundle_data['test_runs'][-1]['attributes']
            if in_bundle_attributes(bundle_attributes, 'kernel.defconfig'):
                print bundle_attributes['kernel.defconfig']
            if in_bundle_attributes(bundle_attributes, 'target'):
                board_instance = bundle_attributes['target']
            if in_bundle_attributes(bundle_attributes, 'kernel.defconfig'):
                kernel_defconfig = bundle_attributes['kernel.defconfig']
                arch, kernel_defconfig_full = kernel_defconfig.split('-')
                kernel_defconfig_base = ''.join(kernel_defconfig_full.split('+')[:1])
                if kernel_defconfig_full == kernel_defconfig_base:
                    kernel_defconfig_full = None
            if in_bundle_attributes(bundle_attributes, 'kernel.version'):
                kernel_version = bundle_attributes['kernel.version']
            if in_bundle_attributes(bundle_attributes, 'device.tree'):
                device_tree = bundle_attributes['device.tree']
            if in_bundle_attributes(bundle_attributes, 'kernel.endian'):
                kernel_endian = bundle_attributes['kernel.endian']
            if in_bundle_attributes(bundle_attributes, 'platform.fastboot'):
                fastboot = bundle_attributes['platform.fastboot']
            if kernel_boot_time is None:
                if in_bundle_attributes(bundle_attributes, 'kernel-boot-time'):
                    kernel_boot_time = bundle_attributes['kernel-boot-time']
            if in_bundle_attributes(bundle_attributes, 'kernel.tree'):
                kernel_tree = bundle_attributes['kernel.tree']
            if in_bundle_attributes(bundle_attributes, 'kernel-image'):
                kernel_image = bundle_attributes['kernel-image']
            if in_bundle_attributes(bundle_attributes, 'kernel-addr'):
                kernel_addr = bundle_attributes['kernel-addr']
            if in_bundle_attributes(bundle_attributes, 'initrd-addr'):
                initrd_addr = bundle_attributes['initrd-addr']
            if in_bundle_attributes(bundle_attributes, 'dtb-addr'):
                dtb_addr = bundle_attributes['dtb-addr']
            if in_bundle_attributes(bundle_attributes, 'dtb-append'):
                dtb_append = bundle_attributes['dtb-append']
            if in_bundle_attributes(bundle_attributes, 'boot_retries'):
                boot_retries = int(bundle_attributes['boot_retries'])
            if in_bundle_attributes(bundle_attributes, 'test.plan'):
                test_plan = bundle_attributes['test.plan']

        # Record the boot log and result
        # TODO: Will need to map device_types to dashboard device types
        if kernel_defconfig and device_type and result:
            if (arch == 'arm' or arch =='arm64') and device_tree is None:
                platform_name = device_map[device_type][0] + ',legacy'
            else:
                if device_tree == 'vexpress-v2p-ca15_a7.dtb':
                    platform_name = 'vexpress-v2p-ca15_a7'
                elif test_plan == 'boot-kvm':
                    if device_tree == 'sun7i-a20-cubietruck.dtb':
                        if device_type == 'dynamic-vm':
                            device_type = 'cubieboard3-kvm-guest'
                            platform_name = device_map[device_type][0]
                        else:
                            device_type = 'cubieboard3-kvm-host'
                            platform_name = device_map[device_type][0]
                    elif device_tree == 'apm-mustang.dtb':
                        if device_type == 'dynamic-vm':
                            device_type = 'mustang-kvm-guest'
                            platform_name = device_map[device_type][0]
                        else:
                            device_type = 'mustang-kvm-host'
                            platform_name = device_map[device_type][0]
                    elif device_tree == 'juno.dtb':
                        if device_type == 'dynamic-vm':
                            device_type = 'juno-kvm-guest'
                            platform_name = device_map[device_type][0]
                        else:
                            device_type = 'juno-kvm-host'
                            platform_name = device_map[device_type][0]
                else:
                    platform_name = device_map[device_type][0]
            print 'Creating boot log for %s' % platform_name
            log = 'boot-%s.txt' % platform_name
            html = 'boot-%s.html' % platform_name
            if args.lab:
                directory = os.path.join(results_directory, kernel_defconfig + '/' + args.lab)
            else:
                directory = os.path.join(results_directory, kernel_defconfig)
            ensure_dir(directory)
            write_file(job_file, log, directory)
            if kernel_boot_time is None:
                kernel_boot_time = '0.0'
            if results.has_key(kernel_defconfig):
                results[kernel_defconfig].append({'device_type': platform_name, 'dt_test_result': dt_test_result, 'dt_tests_passed': dt_tests_passed, 'dt_tests_failed': dt_tests_failed, 'kernel_boot_time': kernel_boot_time, 'result': result})
            else:
                results[kernel_defconfig] = [{'device_type': platform_name, 'dt_test_result': dt_test_result, 'dt_tests_passed': dt_tests_passed, 'dt_tests_failed': dt_tests_failed, 'kernel_boot_time': kernel_boot_time, 'result': result}]
            # Create JSON format boot metadata
            print 'Creating JSON format boot metadata'
            if args.lab:
                boot_meta['lab_name'] = args.lab
            else:
                boot_meta['lab_name'] = None
            if board_instance:
                boot_meta['board_instance'] = board_instance
            boot_meta['retries'] = boot_retries
            boot_meta['boot_log'] = log
            boot_meta['boot_log_html'] = html
            # TODO: Fix this
            boot_meta['version'] = '1.0'
            boot_meta['arch'] = arch
            boot_meta['defconfig'] = kernel_defconfig_base
            if kernel_defconfig_full is not None:
                boot_meta['defconfig_full'] = kernel_defconfig_full
            if device_map[device_type][1]:
                boot_meta['mach'] = device_map[device_type][1]
            boot_meta['kernel'] = kernel_version
            boot_meta['job'] = kernel_tree
            boot_meta['board'] = platform_name
            if board_offline and result == 'FAIL':
                boot_meta['boot_result'] = 'OFFLINE'
                #results[kernel_defconfig]['result'] = 'OFFLINE'
            else:
                boot_meta['boot_result'] = result
            if result == 'FAIL' or result == 'OFFLINE':
                if boot_failure_reason:
                    boot_meta['boot_result_description'] = boot_failure_reason
                else:
                    boot_meta['boot_result_description'] = 'Unknown Error: platform failed to boot'
            boot_meta['boot_time'] = kernel_boot_time
            # TODO: Fix this
            boot_meta['boot_warnings'] = None
            if device_tree:
                boot_meta['dtb'] = 'dtbs/' + device_tree
            else:
                boot_meta['dtb'] = device_tree
            boot_meta['dtb_addr'] = dtb_addr
            boot_meta['dtb_append'] = dtb_append
            boot_meta['dt_test'] = dt_test
            boot_meta['endian'] = kernel_endian
            boot_meta['fastboot'] = fastboot
            # TODO: Fix this
            boot_meta['initrd'] = None
            boot_meta['initrd_addr'] = initrd_addr
            boot_meta['kernel_image'] = kernel_image
            boot_meta['loadaddr'] = kernel_addr
            json_file = 'boot-%s.json' % platform_name
            write_json(json_file, directory, boot_meta)
            print 'Creating html version of boot log for %s' % platform_name
            cmd = 'python log2html.py %s' % os.path.join(directory, log)
            subprocess.check_output(cmd, shell=True)
            if args.lab and args.api and args.token:
                print 'Sending boot result to %s for %s' % (args.api, platform_name)
                headers = {
                    'Authorization': args.token,
                    'Content-Type': 'application/json'
                }
                api_url = urlparse.urljoin(args.api, '/boot')
                response = requests.post(api_url, data=json.dumps(boot_meta), headers=headers)
                print response.content
                headers = {
                    'Authorization': args.token,
                }
                print 'Uploading text version of boot log'
                with open(os.path.join(directory, log)) as lh:
                    data = lh.read()
                api_url = urlparse.urljoin(args.api, '/upload/%s/%s/%s/%s/%s' % (kernel_tree, kernel_version, kernel_defconfig, args.lab, log))
                response = requests.put(api_url, headers=headers, data=data)
                print response.content
                print 'Uploading text version of boot log'
                with open(os.path.join(directory, html)) as lh:
                    data = lh.read()
                api_url = urlparse.urljoin(args.api, '/upload/%s/%s/%s/%s/%s' % (kernel_tree, kernel_version, kernel_defconfig, args.lab, html))
                retry = True
                while retry:
                    response = requests.put(api_url, headers=headers, data=data)
                    if response.status_code != '500':
                        retry = False
                        time.sleep(10)
                print response.content

    if results and kernel_tree and kernel_version:
        print 'Creating boot summary for %s' % kernel_version
        boot = '%s-boot-report.txt' % kernel_version
        passed = 0
        failed = 0
        for defconfig, results_list in results.items():
            for result in results_list:
                if result['result'] == 'PASS':
                    passed += 1
                else:
                    failed += 1
        total = passed + failed
        if args.lab:
            report_directory = os.path.join(results_directory, args.lab)
            mkdir(report_directory)
        else:
            report_directory = results_directory
        with open(os.path.join(report_directory, boot), 'a') as f:
            f.write('To: %s\n' % args.email)
            f.write('From: bot@kernelci.org\n')
            f.write('Subject: %s boot: %s boots: %s passed, %s failed (%s)\n' % (kernel_tree,
                                                                                str(total),
                                                                                str(passed),
                                                                                str(failed),
                                                                                kernel_version))
            f.write('\n')
            f.write('Full Build Report: http://kernelci.org/build/%s/kernel/%s/\n' % (kernel_tree, kernel_version))
            f.write('Full Boot Report: http://kernelci.org/boot/all/job/%s/kernel/%s/\n' % (kernel_tree, kernel_version))
            f.write('\n')
            f.write('Total Duration: %.2f minutes\n' % (duration / 60))
            f.write('Tree/Branch: %s\n' % kernel_tree)
            f.write('Git Describe: %s\n' % kernel_version)
            first = True
            for defconfig, results_list in results.items():
                for result in results_list:
                    if result['result'] == 'OFFLINE':
                        if first:
                            f.write('\n')
                            f.write('Boards Offline:\n')
                            first = False
                        f.write('\n')
                        f.write(defconfig)
                        f.write('\n')
                        break
                for result in results_list:
                    if result['result'] == 'OFFLINE':
                        f.write('    %s   %ss   boot-test: %s\n' % (result['device_type'],
                                                                    result['kernel_boot_time'],
                                                                    result['result']))
                        f.write('\n')
            first = True
            for defconfig, results_list in results.items():
                for result in results_list:
                    if result['result'] == 'FAIL':
                        if first:
                            f.write('\n')
                            f.write('Failed Boot Tests:\n')
                            first = False
                        f.write('\n')
                        f.write(defconfig)
                        f.write('\n')
                        break
                for result in results_list:
                    if result['result'] == 'FAIL':
                        f.write('    %s   %ss   boot-test: %s\n' % (result['device_type'],
                                                                    result['kernel_boot_time'],
                                                                    result['result']))
                        if args.lab:
                            f.write('    http://storage.kernelci.org/kernel-ci/%s/%s/%s/%s/boot-%s.html' % (kernel_tree,
                                                                                                            kernel_version,
                                                                                                            defconfig,
                                                                                                            args.lab,
                                                                                                            result['device_type']))
                        else:
                            f.write('    http://storage.kernelci.org/kernel-ci/%s/%s/%s/boot-%s.html' % (kernel_tree,
                                                                                                         kernel_version,
                                                                                                         defconfig,
                                                                                                         result['device_type']))
                        f.write('\n')
            f.write('\n')
            f.write('Full Boot Report:\n')
            for defconfig, results_list in results.items():
                f.write('\n')
                f.write(defconfig)
                f.write('\n')
                for result in results_list:
                    f.write('    %s   %ss   boot-test: %s\n' % (result['device_type'], result['kernel_boot_time'], result['result']))

    # dt-self-test
    if results and kernel_tree and kernel_version and dt_tests:
        print 'Creating device tree runtime self test summary for %s' % kernel_version
        dt_self_test = '%s-dt-runtime-self-test-report.txt' % kernel_version
        passed = 0
        failed = 0
        for defconfig, results_list in results.items():
            for result in results_list:
                if result['dt_test_result'] == 'PASS':
                    passed += 1
                elif result['dt_test_result'] == 'FAIL':
                    failed += 1
        total = passed + failed
        with open(os.path.join(report_directory, dt_self_test), 'a') as f:
            f.write('To: %s\n' % args.email)
            f.write('From: bot@kernelci.org\n')
            f.write('Subject: %s dt-runtime-unit-tests: %s boards tested: %s passed, %s failed (%s)\n' % (kernel_tree,
                                                                                                           str(total),
                                                                                                           str(passed),
                                                                                                           str(failed),
                                                                                                           kernel_version))
            f.write('\n')
            f.write('Full Build Report: http://kernelci.org/build/%s/kernel/%s/\n' % (kernel_tree, kernel_version))
            f.write('Full Boot Report: http://kernelci.org/boot/all/job/%s/kernel/%s/\n' % (kernel_tree, kernel_version))
            f.write('Full Test Report: http://kernelci.org/test/%s/kernel/%s/\n' % (kernel_tree, kernel_version))
            f.write('\n')
            f.write('Tree/Branch: %s\n' % kernel_tree)
            f.write('Git Describe: %s\n' % kernel_version)
            first = True
            for defconfig, results_list in results.items():
                for result in results_list:
                    if result['dt_test_result'] == 'FAIL':
                        if first:
                            f.write('\n')
                            f.write('Failed Device Tree Unit Tests:\n')
                            first = False
                        f.write('\n')
                        f.write(defconfig)
                        f.write('\n')
                        break
                for result in results_list:
                    if result['dt_test_result'] == "FAIL":
                        f.write('    %s   passed: %s / failed: %s   dt-runtime-unit-tests: %s\n' % (result['device_type'],
                                                                                                    result['dt_tests_passed'],
                                                                                                    result['dt_tests_failed'],
                                                                                                    result['dt_test_result']))
                        if args.lab:
                            f.write('    http://storage.kernelci.org/kernel-ci/%s/%s/%s/%s/boot-%s.html' % (kernel_tree,
                                                                                                        kernel_version,
                                                                                                        defconfig,
                                                                                                        args.lab,
                                                                                                        result['device_type']))
                        else:
                            f.write('    http://storage.kernelci.org/kernel-ci/%s/%s/%s/boot-%s.html' % (kernel_tree,
                                                                                                         kernel_version,
                                                                                                         defconfig,
                                                                                                         result['device_type']))
            f.write('\n')
            f.write('\n')
            f.write('Full Unit Test Report:\n')
            for defconfig, results_list in results.items():
                first = True
                for result in results_list:
                    if result['dt_test_result']:
                        if first:
                            f.write('\n')
                            f.write(defconfig)
                            f.write('\n')
                            first = False
                        f.write('    %s   passed: %s / failed: %s   dt-runtime-unit-tests: %s\n' % (result['device_type'],
                                                                                                    result['dt_tests_passed'],
                                                                                                    result['dt_tests_failed'],
                                                                                                    result['dt_test_result']))

    # sendmail
    if args.email:
        print 'Sending e-mail summary to %s' % args.email
        if os.path.exists(report_directory):
            cmd = 'cat %s | sendmail -t' % os.path.join(report_directory, boot)
            subprocess.check_output(cmd, shell=True)
        if dt_tests:
            if os.path.exists(report_directory):
                cmd = 'cat %s | sendmail -t' % os.path.join(report_directory, dt_self_test)
                subprocess.check_output(cmd, shell=True)

def test_report(args):
    connection, jobs, duration =  parse_json(args.test)
    results_directory = os.getcwd() + '/results'
    mkdir(results_directory)
    for job_id in jobs:
        # Init
        test_meta = {}
        test_cases = []
        api_url = None
        arch = None
        board_instance = None
        boot_retries = 0
        kernel_defconfig_full = None
        kernel_defconfig = None
        kernel_defconfig_base = None
        kernel_version = None
        device_tree = None
        kernel_endian = None
        kernel_tree = None
        kernel_image = None
        kernel_addr = None
        initrd_addr = None
        dtb_addr = None
        dtb_append = None
        fastboot = None
        fastboot_cmd = None
        test_plan = None
        job_file = ''
        dt_test = None
        dt_test_result = None
        dt_tests_passed = None
        dt_tests_failed = None
        board_offline = False
        kernel_boot_time = None
        boot_failure_reason = None
        test_plan = None
        test_set = None
        test_suite = None
        test_type = None
        test_vcs_commit = None
        test_def_uri = None
        print 'Job ID: %s' % job_id
        job_details = connection.scheduler.job_details(job_id)
        if job_details['requested_device_type_id']:
            device_type = job_details['requested_device_type_id']
            platform_name = device_map[device_type][0]
        if job_details['description']:
            job_name = job_details['description']
        result = jobs[job_id]['result']
        bundle = jobs[job_id]['bundle']
        # Retrieve bundle
        if bundle is not None:
            json_bundle = connection.dashboard.get(bundle)
            bundle_data = json.loads(json_bundle['content'])
            # Get the boot data from LAVA
            for test_results in bundle_data['test_runs']:
                # Check for the LAVA test
                if test_results['test_id'] != 'lava':
                    if 'testdef_metadata' in test_results:
                        if 'url' in test_results['testdef_metadata']:
                            test_def_uri = test_results['testdef_metadata']['url']
                        if 'version' in test_results['testdef_metadata']:
                            test_vcs_commit = test_results['testdef_metadata']['version']
                    for test in test_results['test_results']:
                        test_case = {}
                        test_case['name'] = test['test_case_id']
                        test_case['status'] = test['result'].upper()
                        test_case['version'] = '1.0'
                        test_cases.append(test_case)
                    bundle_attributes = bundle_data['test_runs'][-1]['attributes']
            if in_bundle_attributes(bundle_attributes, 'kernel.defconfig'):
                print bundle_attributes['kernel.defconfig']
            if in_bundle_attributes(bundle_attributes, 'target'):
                board_instance = bundle_attributes['target']
            if in_bundle_attributes(bundle_attributes, 'kernel.defconfig'):
                kernel_defconfig = bundle_attributes['kernel.defconfig']
                arch, kernel_defconfig_full = kernel_defconfig.split('-')
                kernel_defconfig_base = ''.join(kernel_defconfig_full.split('+')[:1])
                if kernel_defconfig_full == kernel_defconfig_base:
                    kernel_defconfig_full = None
            if in_bundle_attributes(bundle_attributes, 'kernel.version'):
                kernel_version = bundle_attributes['kernel.version']
            if in_bundle_attributes(bundle_attributes, 'device.tree'):
                device_tree = bundle_attributes['device.tree']
            if in_bundle_attributes(bundle_attributes, 'kernel.endian'):
                kernel_endian = bundle_attributes['kernel.endian']
            if in_bundle_attributes(bundle_attributes, 'platform.fastboot'):
                fastboot = bundle_attributes['platform.fastboot']
            if kernel_boot_time is None:
                if in_bundle_attributes(bundle_attributes, 'kernel-boot-time'):
                    kernel_boot_time = bundle_attributes['kernel-boot-time']
            if in_bundle_attributes(bundle_attributes, 'kernel.tree'):
                kernel_tree = bundle_attributes['kernel.tree']
            if in_bundle_attributes(bundle_attributes, 'kernel-image'):
                kernel_image = bundle_attributes['kernel-image']
            if in_bundle_attributes(bundle_attributes, 'kernel-addr'):
                kernel_addr = bundle_attributes['kernel-addr']
            if in_bundle_attributes(bundle_attributes, 'initrd-addr'):
                initrd_addr = bundle_attributes['initrd-addr']
            if in_bundle_attributes(bundle_attributes, 'dtb-addr'):
                dtb_addr = bundle_attributes['dtb-addr']
            if in_bundle_attributes(bundle_attributes, 'dtb-append'):
                dtb_append = bundle_attributes['dtb-append']
            if in_bundle_attributes(bundle_attributes, 'boot_retries'):
                boot_retries = int(bundle_attributes['boot_retries'])
            if in_bundle_attributes(bundle_attributes, 'test.plan'):
                test_plan = bundle_attributes['test.plan']
            if in_bundle_attributes(bundle_attributes, 'test.set'):
                test_set = bundle_attributes['test.set']
            if in_bundle_attributes(bundle_attributes, 'test.suite'):
                test_suite = bundle_attributes['test.suite']
            if in_bundle_attributes(bundle_attributes, 'test.type'):
                test_type = bundle_attributes['test.type']

            # Create JSON format boot metadata
            print 'Creating JSON format test metadata'
            test_meta['version'] = '1.0'
            test_meta['name'] = test_suite
            if args.lab:
                test_meta['lab_name'] = args.lab
            else:
                test_meta['lab_name'] = None
            test_meta['arch'] = arch
            test_meta['defconfig'] = kernel_defconfig_base
            if kernel_defconfig_full is not None:
                test_meta['defconfig_full'] = kernel_defconfig_full
            if device_map[device_type][1]:
                test_meta['mach'] = device_map[device_type][1]
            test_meta['kernel'] = kernel_version
            test_meta['job'] = kernel_tree
            test_meta['board'] = platform_name
            test_meta['test_set'] = {
                'name': test_set,
                'version': '1.0',
                'definition_uri': test_def_uri,
                'vcs_commit': test_vcs_commit,
                'test_case': test_cases
            }
            json_file = '%s-%s.json' % (test_suite, platform_name)
            write_json(json_file, results_directory, test_meta)
            if args.lab and args.api and args.token:
                print 'Sending test result to %s for %s' % (args.api, platform_name)
                headers = {
                    'Authorization': args.token,
                    'Content-Type': 'application/json'
                }
                api_url = urlparse.urljoin(args.api, '/test-suite')
                response = requests.post(api_url, data=json.dumps(test_meta), headers=headers)
                print response.content

def main(args):
    if args.boot:
        boot_report(args)
    if args.test:
        test_report(args)
    exit(0)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--boot", help="creates a kernel-ci boot report from a given json file")
    parser.add_argument("--test", help="creates a kernel-ci test report from a given json file")
    parser.add_argument("--lab", help="lab id")
    parser.add_argument("--api", help="api url")
    parser.add_argument("--token", help="authentication token")
    parser.add_argument("--email", help="email address to send report to")
    args = parser.parse_args()
    main(args)
