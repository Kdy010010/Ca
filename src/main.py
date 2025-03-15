import re
import sys
import os

def ca_to_nasm(ca_code):
    variables = {}
    functions = {}
    arrays = {}
    dictionaries = {}
    nasm_code = []
    
    data_section = [
        "section .data", 
        "fmt db '%d', 0", 
        "newline db 10, 0", 
        "input_buffer db 256, 0"
    ]
    
    bss_section = ["section .bss"]
    text_section = ["section .text", "global _start"]
    main_function = []
    current_function = None
    condition_count = 0
    loop_count = 0
    switch_count = 0
    
    inside_asm = False
    asm_code = []

    for line in ca_code.splitlines():
        line = line.strip()
        
        # 인라인 어셈블리 시작
        if line.startswith("asm {"):
            inside_asm = True
            asm_code = []
            continue
        
        # 인라인 어셈블리 종료
        elif line.startswith("}") and inside_asm:
            inside_asm = False
            text_section.extend(asm_code)
            continue
        
        # 인라인 어셈블리 코드 추가
        if inside_asm:
            asm_code.append(f"    {line}")
            continue

        # 라이브러리 import
        if line.startswith("import"):
            _, lib_name = line.split()
            lib_path = f"libs/{lib_name}.ca"
            if os.path.exists(lib_path):
                with open(lib_path, 'r', encoding='utf-8') as lib_file:
                    ca_code += '\n' + lib_file.read()
        
        # 네임스페이스 지원
        elif line.startswith("namespace"):
            _, ns_name = line.split()
            text_section.append(f"    ; Namespace: {ns_name}")
        
        # 변수 선언
        elif line.startswith("var"):
            parts = line.split()[1:]
            value = parts[-1]
            for var_name in parts[:-1]:
                if value.startswith("\"") and value.endswith("\""):
                    data_section.append(f"    {var_name} db {value}, 0")
                else:
                    data_section.append(f"    {var_name} dd {value}")
                variables[var_name] = value
        
        # 함수 정의
        elif line.startswith("func"):
            _, func_name = line.split()
            current_function = func_name
            functions[func_name] = [f"{func_name}:"]

        elif line.startswith("return"):
            _, reg = line.split()
            functions[current_function].append(f"    mov eax, {reg}")
            functions[current_function].append("    ret")
            current_function = None
        
        elif line.startswith("endfunc"):
            if current_function:
                functions[current_function].append("    ret")
                current_function = None
        
        # if-elif-else 문
        elif line.startswith("if"):
            condition_count += 1
            _, condition = line.split(maxsplit=1)
            text_section.append(f"    cmp {condition}")
            text_section.append(f"    jne endif_{condition_count}")

        elif line.startswith("else"):
            text_section.append(f"    jmp endelse_{condition_count}")
            text_section.append(f"endif_{condition_count}:")

        elif line.startswith("endif"):
            text_section.append(f"endelse_{condition_count}:")

        # print 명령
        elif line.startswith("print"):
            _, reg = line.split()
            text_section.append(f"    mov edi, fmt")
            text_section.append(f"    mov esi, {reg}")
            text_section.append("    call printf")
        
        # scan (사용자 입력)
        elif line.startswith("scan"):
            _, var = line.split()
            text_section.append("    mov eax, 0")
            text_section.append("    mov edi, input_buffer")
            text_section.append("    mov edx, 256")
            text_section.append("    syscall")
            text_section.append(f"    mov [{var}], edi")
        
        # exit (프로그램 종료)
        elif line.startswith("exit"):
            text_section.append("    mov eax, 60")
            text_section.append("    xor edi, edi")
            text_section.append("    syscall")
    
    text_section.append("_start:")
    text_section.extend(main_function)

    for func in functions.values():
        text_section.extend(func)

    return "\n".join(data_section + bss_section + text_section)

def process_ca_file(input_filename, output_filename):
    with open(input_filename, 'r', encoding='utf-8') as infile:
        ca_code = infile.read()
    
    nasm_code = ca_to_nasm(ca_code)
    
    with open(output_filename, 'w', encoding='utf-8') as outfile:
        outfile.write(nasm_code)

def main():
    if len(sys.argv) != 3:
        print("Usage: python compiler.py <input.ca> <output.nasm>")
        sys.exit(1)
    
    input_filename = sys.argv[1]
    output_filename = sys.argv[2]
    process_ca_file(input_filename, output_filename)
    print(f"Converted {input_filename} to {output_filename}")

if __name__ == "__main__":
    main()
