#include <efi.h>
#include <efilib.h>

static void print_ip(CHAR16 *label, UINT8 *ip) {
    Print(L"%s %d.%d.%d.%d\n",
        label,
        ip[0],
        ip[1],
        ip[2],
        ip[3]);
}

EFI_STATUS efi_main(EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable) {
    InitializeLib(ImageHandle, SystemTable);

    Print(L"\n=== PXE INFO ===\n");

    EFI_LOADED_IMAGE *loadedImage;
    EFI_STATUS status = uefi_call_wrapper(
        BS->HandleProtocol,
        3,
        ImageHandle,
        &LoadedImageProtocol,
        (void**)&loadedImage
    );

    if (!EFI_ERROR(status) && loadedImage) {
        CHAR16 *loadedImagePath = DevicePathToStr(loadedImage->FilePath);
        if (loadedImagePath && StrLen(loadedImagePath)) {
            Print(L"Image path: %s\n", loadedImagePath);
        } else {
            Print(L"Image path: <empty>\n");
        }

        // TODO: Print the actual loaded options
        // https://uefi.org/specs/UEFI/2.10/03_Boot_Manager.html#load-options
        Print(L"LoadOptionsSize: %d\n", loadedImage->LoadOptionsSize);
    } else {
        Print(L"Failed to get LoadedImage\n");
    }

    EFI_PXE_BASE_CODE_PROTOCOL *pxe;
    status = uefi_call_wrapper(
        BS->LocateProtocol,
        3,
        &PxeBaseCodeProtocol,
        NULL,
        (void**)&pxe
    );

    if (!EFI_ERROR(status) && pxe && pxe->Mode && pxe->Mode->DhcpAckReceived) {
        EFI_PXE_BASE_CODE_DHCPV4_PACKET *pkt = &pxe->Mode->DhcpAck.Dhcpv4;
        print_ip(L"Client IP:", pkt->BootpYiAddr);
        print_ip(L"Boot Server IP:", pkt->BootpSiAddr);
        if (pkt->BootpBootFile && strlena(pkt->BootpBootFile)) {
            Print(L"Boot File: %a\n", pkt->BootpBootFile);
        } else {
            Print(L"Boot File: <empty>\n", pkt->BootpBootFile);
        }
    } else {
        Print(L"PXE protocol not available or no ACK received\n");
    }

    Print(L"\nPress any key to continue\n");
    EFI_INPUT_KEY key;
    UINTN index;
    uefi_call_wrapper(ST->ConIn->Reset, 2, ST->ConIn, FALSE);
    uefi_call_wrapper(BS->WaitForEvent, 3, 1, &ST->ConIn->WaitForKey, &index);
    uefi_call_wrapper(ST->ConIn->ReadKeyStroke, 2, ST->ConIn, &key);

    return EFI_SUCCESS;
}
