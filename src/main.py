import re
import sys
import os

def ca_to_nasm(ca_code):
    variables = {}
    functions = {}
    imported_libs = set()
    loop_stack = []
    condition_count = 0
    loop_count = 0
    # extern 제거, 32비트 real mode용, bits 32 대신 real 모드에서는 "bits 16"이나 적절한 설정 필요하나
    # 여기서는 간략화를 위해 bits 32로 작성 (실제 환경에 맞게 수정 필요)
    text_section = ["section .text", "global _start", "bits 32"]
    # data_section: 문자열 등 저장
    data_section = ["section .data", "newline db 10, 0"]
    # bss_section: 입력 버퍼와 정수 변환용 버퍼 추가
    bss_section = ["section .bss", "input_buffer resb 256", "int_buffer resb 12"]
    main_function = []
    current_function = None
    inside_asm = False
    asm_code = []
    
    for line in ca_code.splitlines():
        line = line.strip()
        
        # 인라인 어셈블리 지원
        if line.startswith("asm {"):
            inside_asm = True
            asm_code = []
            continue
        elif inside_asm and line.startswith("}"):
            inside_asm = False
            text_section.extend(asm_code)
            continue
        elif inside_asm:
            asm_code.append(f"    {line}")
            continue
        
        # 라이브러리 import (bare bones 모드에서는 직접 include)
        if line.startswith("import"):
            _, lib_name = line.split()
            if lib_name not in imported_libs:
                imported_libs.add(lib_name)
                lib_path = f"libs/{lib_name}.ca"
                if os.path.exists(lib_path):
                    with open(lib_path, 'r', encoding='utf-8') as lib_file:
                        ca_code += '\n' + lib_file.read()
        
        # 변수 선언: 문자열은 data 섹션, 나머지는 bss 섹션에 저장
        elif line.startswith("var"):
            parts = line.split()[1:]
            value = parts[-1]
            for var_name in parts[:-1]:
                if value.startswith("\"") and value.endswith("\""):
                    data_section.append(f"    {var_name} db {value}, 0")
                else:
                    bss_section.append(f"    {var_name} resd 1")
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
        
        # 조건문 (if, else, endif)
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
        
        # while 루프
        elif line.startswith("while"):
            loop_count += 1
            _, condition = line.split(maxsplit=1)
            start_label = f"while_start_{loop_count}"
            end_label = f"while_end_{loop_count}"
            text_section.append(f"{start_label}:")
            text_section.append(f"    cmp {condition}")
            text_section.append(f"    je {end_label}")
            loop_stack.append((start_label, end_label))
        elif line.startswith("endwhile"):
            if loop_stack:
                start_label, end_label = loop_stack.pop()
                text_section.append(f"    jmp {start_label}")
                text_section.append(f"{end_label}:")
        
        # print 명령 (정수/문자열 자동 구분)
        elif line.startswith("print"):
            _, reg = line.split()
            # 문자열이면 print_str, 정수이면 print_int 호출
            if reg in variables and variables[reg].startswith("\""):
                text_section.append(f"    mov esi, {reg}")
                text_section.append("    call print_str")
            else:
                text_section.append(f"    mov eax, {reg}")
                text_section.append("    call print_int")
        
        # scan 명령: 변수 타입에 따라 분기 (문자열이면 copy, 정수이면 atoi 후 저장)
        elif line.startswith("scan"):
            _, var = line.split()
            text_section.append("    call scan")
            if var in variables and variables[var].startswith("\""):
                # 문자열 변수: input_buffer -> 대상 메모리 복사
                text_section.append("    mov esi, input_buffer")
                text_section.append(f"    lea edi, [{var}]")
                text_section.append("    call copy_str")
            else:
                # 정수 변수: 입력 문자열을 정수로 변환하여 저장
                text_section.append("    call atoi")
                text_section.append(f"    mov [{var}], eax")
        
        # exit 명령: 무한 루프로 종료
        elif line.startswith("exit"):
            text_section.append("    jmp hang")
    
    text_section.append("_start:")
    text_section.extend(main_function)
    for func in functions.values():
        text_section.extend(func)
    
    # bare bones용 서브루틴들
    subroutines = [
        "",
        ";-------------------------------------------------------",
        "; print_str: VGA 텍스트 버퍼(0xb8000)로 null-terminated 문자열 출력",
        "print_str:",
        "    push ebp",
        "    mov ebp, esp",
        "    mov edi, 0xb8000",
        "print_str_loop:",
        "    mov al, byte [esi]",
        "    cmp al, 0",
        "    je print_str_done",
        "    mov byte [edi], al",
        "    mov byte [edi+1], 0x07",
        "    inc esi",
        "    add edi, 2",
        "    jmp print_str_loop",
        "print_str_done:",
        "    pop ebp",
        "    ret",
        ";-------------------------------------------------------",
        "; print_int: 정수(EAX)에 대해 int_buffer에 숫자 문자열로 변환 후 print_str 호출",
        "print_int:",
        "    push ebp",
        "    mov ebp, esp",
        "    push ebx",
        "    push ecx",
        "    push edx",
        "    ; int_buffer의 끝 주소 계산 (int_buffer + 11, null terminator 위치)",
        "    mov edi, int_buffer",
        "    add edi, 11",
        "    mov byte [edi], 0",
        "    ; 만약 EAX가 0이면 바로 '0' 출력",
        "    cmp eax, 0",
        "    jne .convert_int",
        "    mov byte [edi-1], '0'",
        "    lea esi, [edi-1]",
        "    jmp .print_int_done",
        ".convert_int:",
        "    ; 부호 판별: 음수이면 부호 플래그를 BL에 1로 설정하고 EAX를 양수로 변환",
        "    mov bl, 0",
        "    cmp eax, 0",
        "    jge .conv_loop",
        "    mov bl, 1",
        "    neg eax",
        ".conv_loop:",
        "    ; 10으로 나누어 자릿수 추출 (나머지를 '0'의 ASCII 값과 합산)",
        "    xor edx, edx",
        "    mov ecx, 10",
        "    div ecx        ; EAX = EAX/10, EDX = 나머지",
        "    add dl, '0'",
        "    dec edi",
        "    mov [edi], dl",
        "    cmp eax, 0",
        "    jne .conv_loop",
        "    ; 음수이면 '-' 문자 추가",
        "    cmp bl, 1",
        "    jne .print_int_done",
        "    dec edi",
        "    mov byte [edi], '-'",
        ".print_int_done:",
        "    lea esi, [edi]",
        "    call print_str",
        "    pop edx",
        "    pop ecx",
        "    pop ebx",
        "    pop ebp",
        "    ret",
        ";-------------------------------------------------------",
        "; scan: BIOS 인터럽트(0x16)를 사용하여 키보드 입력을 input_buffer에 저장, 엔터(13) 입력 시 종료",
        "scan:",
        "    push ebp",
        "    mov ebp, esp",
        "    lea edi, [input_buffer]",
        ".scan_loop:",
        "    mov ah, 0",
        "    int 0x16",         ; 키 입력 대기 (AL에 ASCII 코드)
        "    cmp al, 13",       ; Enter (CR) 검사",
        "    je .end_scan",
        "    mov [edi], al",
        "    inc edi",
        "    jmp .scan_loop",
        ".end_scan:",
        "    mov byte [edi], 0",  ; null-terminate",
        "    pop ebp",
        "    ret",
        ";-------------------------------------------------------",
        "; atoi: input_buffer에 있는 null-terminated 문자열을 정수로 변환하여 EAX에 반환",
        "atoi:",
        "    push ebp",
        "    mov ebp, esp",
        "    mov esi, input_buffer",
        "    ; 공백 건너뛰기",
        ".skip_spaces:",
        "    mov al, [esi]",
        "    cmp al, ' '",
        "    je .skip_spaces_inc",
        "    jmp .check_sign",
        ".skip_spaces_inc:",
        "    inc esi",
        "    jmp .skip_spaces",
        ".check_sign:",
        "    mov ebx, 1      ; 부호: +1",
        "    cmp byte [esi], '-'",
        "    jne .check_positive",
        "    mov ebx, -1     ; 부호: -1",
        "    inc esi",
        "    jmp .convert_digits",
        ".check_positive:",
        "    cmp byte [esi], '+'",
        "    je .skip_plus",
        ".convert_digits:",
        "    xor eax, eax    ; 결과 누적용",
        ".convert_loop:",
        "    movzx edx, byte [esi]",
        "    cmp edx, 0",
        "    je .done_atoi",
        "    cmp edx, '0'",
        "    jb .done_atoi",
        "    cmp edx, '9'",
        "    ja .done_atoi",
        "    imul eax, eax, 10",
        "    sub edx, '0'",
        "    add eax, edx",
        "    inc esi",
        "    jmp .convert_loop",
        ".skip_plus:",
        "    inc esi",
        "    jmp .convert_digits",
        ".done_atoi:",
        "    cmp ebx, 1",
        "    je .apply_sign_done",
        "    neg eax",
        ".apply_sign_done:",
        "    pop ebp",
        "    ret",
        ";-------------------------------------------------------",
        "; copy_str: ESI에 있는 null-terminated 문자열을 EDI가 가리키는 곳으로 복사",
        "copy_str:",
        "    push ebp",
        "    mov ebp, esp",
        ".copy_loop:",
        "    mov al, [esi]",
        "    mov [edi], al",
        "    cmp al, 0",
        "    je .done_copy",
        "    inc esi",
        "    inc edi",
        "    jmp .copy_loop",
        ".done_copy:",
        "    pop ebp",
        "    ret",
        ";-------------------------------------------------------",
        "; hang: 프로그램 종료 대신 무한 루프",
        "hang:",
        "    jmp hang"
    ]
    
    text_section.extend(subroutines)
    
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
