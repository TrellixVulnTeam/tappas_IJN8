import contextlib
import logging
import os
import subprocess
import tarfile
from enum import Enum
from pathlib import Path


class Arch(Enum):
    AARCH64 = 'aarch64'
    ARMV7L = 'armv7l'
    ARMV7LHF = 'armv7lhf'

    def __str__(self):
        return self.value


@contextlib.contextmanager
def working_directory(target_directory):
    current_directory = os.getcwd()
    try:
        os.chdir(target_directory)
        yield target_directory
    finally:
        os.chdir(current_directory)


def run_subprocess(command_line, logger, check_output=True, cwd=None, shell=False, update_env=None):
    if update_env is None:
        update_env = {}

    current_env = os.environ.copy()
    for key, value in update_env.items():
        current_env[key] = value
    if shell:
        output = subprocess.run(command_line, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=current_env,
                                shell=True)
    else:
        output = subprocess.run(command_line.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                                env=current_env, shell=False)
    if check_output:
        check_subprocess_output(output, logger)


def check_subprocess_output(subprocess_output, logger):
    cmd = " ".join(subprocess_output.args)
    return_code = subprocess_output.returncode
    subprocess_stdout = subprocess_output.stdout.decode()
    subprocess_stderr = subprocess_output.stderr.decode()

    log_message = "CMD <{}> RETURNED <{}>.\n".format(cmd, return_code)

    if subprocess_stdout:
        log_message += '{}STDOUT was:\n{}\n'.format(log_message, subprocess_stdout)
    if subprocess_stderr:
        log_message += '{}STDERR was:\n{}\n'.format(log_message, subprocess_stderr)
    if return_code == 0:
        try:
            logger.debug(log_message)
        except Exception:
            logger.warning("An error occurred when trying to logging the output date")
            logger.debug("Encoded log message:\n{}".format(log_message.encode('utf-8')))
    else:
        try:
            logger.error("An error occurred when running a sub-process: {}".format(log_message))
        except Exception:
            logger.error("An error occurred when trying to logging the output date")
            logger.error("Encoded log message:\n{}".format(log_message.encode('utf-8')))
        raise subprocess.CalledProcessError(return_code, cmd, subprocess_stdout, subprocess_stderr)


def extract_and_install_toolchain(tar_path, dir_to_install_toolchain_in, logger):
    logger.info('extracting toolchain')
    tar_dir = os.path.dirname(tar_path)

    with tarfile.open(tar_path, "r:gz") as tar_file:
        toolchain_installers = [tar_path.parent / Path(member.name) for member in tar_file.getmembers() if
                                '.sh' in member.name]

        if len(toolchain_installers) == 0:
            raise FileNotFoundError("No toolchain installer found")

        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(tar_file, path=tar_dir)

    logger.info('installing toolchain')
    for toolchain_installer in toolchain_installers:
        logger.info("installing {}".format(toolchain_installer))
        run_subprocess("{} -d {} -y".format(toolchain_installer, dir_to_install_toolchain_in), logger=logger)


class ShellRunner:
    """Object dedicated for running and logging shell commands."""

    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger('shell_runner')

    def run(self, shell_cmd, env=None, ignore_errors=False, timeout=None, shell=False, cwd=None):
        """
        Run a command in a subprocess
        :param shell: should run in shell mode? PAY ATTENTION: if shell=True pass the command as string and not
         as array of strings
        :param shell_cmd: The shell command as list of string --> f.e ['python', '-c', ...]
        :param env: environment data as dict
        :param ignore_errors: if True the output of the subprocess would be checked and if failed an
         exception would be raised
        :param timeout: Amount of seconds before the subprocess will be timed out and raise TimeoutExpired exception
        :param cwd: directory to run from
        :return: stdout, stderr, return_code
        """
        if type(shell_cmd) is list:
            shell_cmd = self._convert_pathlib_instance_to_str(shell_cmd)

        p = subprocess.run(shell_cmd, cwd=cwd, shell=shell, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, stdin=subprocess.PIPE,
                           env=env, timeout=timeout)

        p.stdout = p.stdout.decode()
        p.stderr = p.stderr.decode()

        self._log_subprocess(p)
        if not ignore_errors:
            p.check_returncode()

        return p

    def _convert_pathlib_instance_to_str(self, arr):
        """
        Provide support to auto convert Path-lib to str
        """
        shell_cmd = [str(word) if type(word) is Path else word
                     for word in arr]
        return shell_cmd

    def _log_subprocess(self, subprocess_results):
        out = subprocess_results.stdout
        err = subprocess_results.stderr
        return_code = subprocess_results.returncode
        cmd = " ".join([str(w) for w in subprocess_results.args])

        log_message = "CMD <{}> RETURNED <{}>.\n".format(cmd, return_code)
        if out:
            log_message = '{}STDOUT was:\n{}\n'.format(log_message, out)
        if err:
            log_message = '{}STDERR was:\n{}\n'.format(log_message, err)

        if return_code == 0:
            self._logger.debug(log_message)
        else:
            self._logger.error("An error occurred when running a sub-process: {}".format(log_message))


def install_compilers_apt_packages(arch):
    runner = ShellRunner()

    if arch == Arch.ARMV7L:
        apt_packages = ["g++-arm-linux-gnueabi", "gcc-arm-linux-gnueabi"]
    elif arch == Arch.ARMV7LHF:
        apt_packages = ["g++-arm-linux-gnueabihf", "gcc-arm-linux-gnueabihf"]
    else:
        apt_packages = [f'g++-{arch.value}-linux-gnu', f'gcc-{arch.value}-linux-gnu']

    runner.run(shell_cmd=f'sudo apt-get install -y {" ".join(apt_packages)}', shell=True)
