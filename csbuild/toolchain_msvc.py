# Copyright (C) 2013 Jaedyn K. Draper
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import platform
import subprocess

from csbuild import toolchain

### Reference: http://msdn.microsoft.com/en-us/library/f35ctcxw.aspx

X64 = "X64"
X86 = "X86"

HAS_SET_VC_VARS = False
WINDOWS_SDK_DIR = ""

class toolchain_msvc(toolchain.toolchainBase):
    '''Helper class for interfacing with the MSVC toolchain.'''

    def __init__(self):
        toolchain.toolchainBase.__init__(self)

        self.msvc_version = 100
        self._project_settings = None

    def SetupForProject(self, project):
        platform_architectures = {
            "amd64": X64,
            "x86_64": X64,
            "x86": X86,
            "i386": X86}

        self._project_settings = project.settings
        self._vc_env_var = r"VS{}COMNTOOLS".format(self.msvc_version)
        self._toolchain_path = os.path.normpath(os.path.join(os.environ[self._vc_env_var], "..", "..", "VC"))
        self._bin_path = os.path.join(self._toolchain_path, "bin")
        self._include_path = [os.path.join(self._toolchain_path, "include")]
        self._lib_path = [os.path.join(self._toolchain_path, "lib")]
        self._platform_arch = platform_architectures.get(platform.machine().lower(), X86)
        self._build_64_bit = False

        # Determine if we need to build for 64-bit.
        if self._platform_arch == X64 and not self._project_settings.force_64_bit and not self._project_settings.force_32_bit:
            self._build_64_bit = True
        elif self._project_settings.force_64_bit:
            self._build_64_bit = True

        # If we're trying to build for 64-bit, determine the appropriate path for the 64-bit tools based on the machine's architecture.
        if self._build_64_bit:
            #TODO: Switch the assembler to ml64.exe when assemblers are supported.
            self._bin_path = os.path.join(self._bin_path, "amd64" if self._platform_arch == X64 else "x64_amd64")
            self._lib_path[0] = os.path.join(self._lib_path[0], "amd64")

        global HAS_SET_VC_VARS
        global WINDOWS_SDK_DIR
        if not HAS_SET_VC_VARS:

            batch_file_path = os.path.join(self._toolchain_path, "vcvarsall.bat")
            fd = subprocess.Popen('"{}" {} & set'.format(batch_file_path, "x64" if self._build_64_bit else "x86"), stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            (output, errors) = fd.communicate()
            output_lines = output.splitlines()

            for line in output_lines:
                if line.startswith("WindowsSdkDir="):
                    key_value_list = line.split("=", 1)
                    WINDOWS_SDK_DIR = key_value_list[1]
                    break

            HAS_SET_VC_VARS = True

        self._include_path.append(os.path.join(WINDOWS_SDK_DIR, "include"))
        self._lib_path.append(os.path.join(WINDOWS_SDK_DIR, "lib", "x64" if self._build_64_bit else ""))


    ### Private methods ###

    def _get_compiler_exe(self):
        return '"{}" '.format(os.path.join(self._bin_path, "cl"))


    def _get_linker_exe(self):
        return '"{}" '.format(os.path.join(self._bin_path, "link"))


    def _get_default_compiler_args(self):
        return '/nologo /c /arch:AVX '


    def _get_default_linker_args(self):
        default_args = "/NOLOGO /SUBSYSTEM:WINDOWS /SUBSYSTEM:CONSOLE "
        for lib_path in self._lib_path:
            default_args += '/LIBPATH:"{}" '.format(lib_path)
        return default_args


    def _get_compiler_args(self):
        return "{}{}{}{}{}".format(
            self._get_default_compiler_args(),
            self._get_preprocessor_definition_args(),
            self._get_runtime_linkage_arg(),
            self._get_warning_args(),
            self._get_include_directory_args())


    def _get_linker_args(self, output_file, obj_list):
        return "{}{}{}{}{}{}{}{}{}{}".format(
            self._get_default_linker_args(),
            self._get_runtime_library_arg(),
            self._get_architecture_arg(),
            "/PROFILE " if self._project_settings.profile else "",
            "/DEBUG " if self._project_settings.profile or self._project_settings.debug_level > 0 else "",
            "/DLL " if self._project_settings.shared else "",
            self._get_library_directory_args(),
            self._get_linker_output_arg(output_file),
            self._get_library_args(),
            self._get_linker_obj_file_args(obj_list))


    def _get_preprocessor_definition_args(self):
        define_args = ""

        # Add the defines.
        for define_name in self._project_settings.defines:
            define_args += "/D{} ".format(define_name)

        # Add the undefines.
        for define_name in self._project_settings.undefines:
            define_args += "/U{} ".format(define_name)

        return define_args


    def _get_architecture_arg(self):
        return "/MACHINE:{} ".format("X64" if self._build_64_bit else "X86")


    def _get_runtime_linkage_arg(self):
        return "/{}{} ".format(
            "MT" if self._project_settings.static_runtime else "MD",
            "d" if self._project_settings.debug_runtime else "")


    def _get_runtime_library_arg(self):
        return '/DEFAULTLIB:{}{}.lib '.format(
            "libcmt" if self._project_settings.static_runtime else "msvcrt",
            "d" if self._project_settings.debug_runtime else "")

    def _get_library_args(self):
        #args = "kernel32.lib user32.lib gdi32.lib winspool.lib comdlg32.lib advapi32.lib shell32.lib ole32.lib oleaut32.lib uuid.lib odbc32.lib odbccp32.lib "
        args = ""
        for lib in self._project_settings.libraries:
            args += '"{}" '.format(lib)

        return args


    def _get_warning_args(self):
        #TODO: Support additional warning options.
        if self._project_settings.no_warnings:
            return "/w "
        elif self._project_settings.warnings_as_errors:
            return "/WX "

        return ""


    def _get_include_directory_args(self):
        include_dir_args = ""

        for inc_dir in self._project_settings.include_dirs:
            include_dir_args += '/I"{}" '.format(os.path.normpath(inc_dir))

        # The default include paths should be added last so that any paths set by the user get searched first.
        for inc_dir in self._include_path:
            include_dir_args += '/I"{}" '.format(inc_dir)

        return include_dir_args


    def _get_library_directory_args(self):
        library_dir_args = ""

        for lib_dir in self._project_settings.library_dirs:
            library_dir_args += '/LIBPATH:"{}" '.format(os.path.normpath(lib_dir))

        return library_dir_args


    def _get_linker_output_arg(self, output_file):
        return '/OUT:"{}" '.format(output_file)


    def _get_linker_obj_file_args(self, obj_file_list):
        args = ""
        for obj_file in obj_file_list:
            args += '"{} "'.format(obj_file)

        return args


    ### Public methods ###

    def getCompilerCommand(self):
        return "{}{}{}".format(
            self._get_compiler_exe(),
            self._get_compiler_args(),
            self._project_settings.extra_flags)


    def getExtendedCompilerArgs(self, base_cmd, force_include_file, output_obj, input_file):
        return '{}/Fo"{}" "{}"'.format(
            base_cmd,
            output_obj,
            input_file)


    def getLinkerCommand(self, output_file, obj_list):
        return "{}{}".format(
            self._get_linker_exe(),
            self._get_linker_args(output_file, obj_list))


    ### Required functions ###

    def find_library(self, library, library_dirs):

        for lib_dir in library_dirs:
            lib_file_path = os.path.join(lib_dir, library)

            # Do a simple check to see if the file exists.
            if os.path.exists(lib_file_path):
                return lib_file_path

        # The library wasn't found.
        return None


    def get_base_cxx_command(self, project):
        self.SetupForProject(project)
        return self.getCompilerCommand()


    def get_base_cc_command(self, project):
        self.SetupForProject(project)
        return self.getCompilerCommand()


    def get_link_command(self, project, outputFile, objList):
        self.SetupForProject(project)
        return self.getLinkerCommand(outputFile, objList)


    def get_extended_command(self, baseCmd, project, forceIncludeFile, outObj, inFile):
        self.SetupForProject(project)
        return self.getExtendedCompilerArgs(baseCmd, forceIncludeFile, outObj, inFile)


    interrupt_exit_code = -1

    def SetMsvcVersion(self, msvc_version):
        self.msvc_version = msvc_version

