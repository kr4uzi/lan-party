ARCH ?= x86_64

EFI_INC      = /usr/include/efi
EFI_INC_ARCH = $(EFI_INC)/$(ARCH)
EFI_LIB      = /usr/lib

BASE_TARGET = pxeinfo

ifeq ($(ARCH),x86_64)
    CC = x86_64-linux-gnu-gcc
    LD = x86_64-linux-gnu-ld
    OBJCOPY = objcopy
    EFI_TARGET = x86_64
    ARCH_NAME = x64
    CFLAGS_EXTRA = -mno-red-zone
endif

ifeq ($(ARCH),ia32)
    CC = i686-linux-gnu-gcc
    LD = i686-linux-gnu-ld
    OBJCOPY = objcopy
    EFI_TARGET = ia32
    ARCH_NAME = ia32
    CFLAGS_EXTRA =
endif

ifeq ($(ARCH),arm)
    CC = arm-linux-gnueabi-gcc
    LD = arm-linux-gnueabi-ld
    OBJCOPY = objcopy
    EFI_TARGET = arm
    ARCH_NAME = arm
    CFLAGS_EXTRA =
endif

ifeq ($(ARCH),aarch64)
    CC = aarch64-linux-gnu-gcc
    LD = aarch64-linux-gnu-ld
    OBJCOPY = objcopy
    EFI_TARGET = aarch64
    ARCH_NAME = aa64
    CFLAGS_EXTRA =
endif

TARGET = $(BASE_TARGET)$(ARCH_NAME)

# --- Flags ---
CFLAGS = -I$(EFI_INC) -I$(EFI_INC_ARCH) \
         -fpic -fshort-wchar \
         -ffreestanding -fno-stack-protector \
         $(CFLAGS_EXTRA)

LDFLAGS = -nostdlib -znocombreloc \
          -T $(EFI_LIB)/elf_$(EFI_TARGET)_efi.lds \
          -shared -Bsymbolic

LIBS = -L$(EFI_LIB) -lefi -lgnuefi

CRT = $(EFI_LIB)/crt0-efi-$(EFI_TARGET).o


all: $(TARGET).efi

$(TARGET).o: $(BASE_TARGET).c
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET).so: $(TARGET).o
	$(LD) $(LDFLAGS) $(CRT) $< -o $@ $(LIBS)

$(TARGET).efi: $(TARGET).so
	$(OBJCOPY) \
		--target=efi-app-$(EFI_TARGET) \
		-j .text \
		-j .sdata \
		-j .data \
		-j .dynamic \
		-j .dynsym \
		-j .rel \
		-j .rela \
		-j .reloc \
		$< $@

clean:
	rm -f *.o *.so *.efi

all-arch:
	$(MAKE) ARCH=x86_64
	$(MAKE) ARCH=ia32
	$(MAKE) ARCH=arm
	$(MAKE) ARCH=aarch64