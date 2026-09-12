from __future__ import annotations

SECURE_BOOT_GUIDS = {
    "PkVar": "CC0F8A3F-3DEA-4376-9679-5426BA0A907E",
    "KekVar": "9FE7DE69-0AEA-470A-B50A-139813649189",
    "dbVar": "FBF95065-427F-47B3-8077-D13C60710998",
    "dbxVar": "9D7A05E9-F740-44C3-858B-75586A8F9C8E",
}
PATCH_TARGETS = ("PkVar", "KekVar", "dbVar")
LZMA_CUSTOM_DECOMPRESS_GUID = "EE4E5898-3914-4259-9D6E-DC7BD79403CF"
EFI_CERT_X509_GUID = "A5C059A1-94E4-4AA7-87B5-AB155C2BF072"
EFI_CERT_SHA256_GUID = "C1C41626-504C-4092-ACA9-41F936934328"
EFI_CERT_TYPE_PKCS7_GUID = "4AAFD29D-68DF-49EE-8AA9-347D375665A7"

CERT_STRINGS = {
    "ami_test_pk": "DO NOT TRUST - AMI Test PK",
    "kek_2011": "Microsoft Corporation KEK CA 2011",
    "kek_2023": "Microsoft Corporation KEK 2K CA 2023",
    "db_uefi_2011": "Microsoft Corporation UEFI CA 2011",
    "db_windows_2011": "Microsoft Windows Production PCA 2011",
    "db_windows_2023": "Windows UEFI CA 2023",
    "db_microsoft_2023": "Microsoft UEFI CA 2023",
    "db_optionrom_2023": "Microsoft Option ROM UEFI CA 2023",
}

# Exact decompressed payload identity used for generic PK recognition.
VALIDATED_PK_PAYLOAD_SHA256 = "0ad9104d868b315b4b6d6c01a4b51451173f22fc3367cc0c2d482c0a3b1b2e9a"

# Exact validated Secure Boot update payloads bundled with this build.
BUNDLED_DONOR_SHA256 = {
    "PkVar": "6ad2c119c70b4325ad29138c65d0ddafd09cdba299d34fdcb4e3f2aa01b1e7dd",
    "KekVar": "6b8bcfd771d6efcba8459d62d2a8687a252671d66ea0f22ee6aa2140ac8e802a",
    "dbVar": "744662e5b2c92171cf777d36a6b4e3c59d2a6d99ffe4914a41f6a7a2a24f779a",
}
UEFIREPLACE_VERSION = "0.28.0"
UEFIREPLACE_SHA256 = "ab05d53fcac19651818f4ee4505813b10badec7a10d141836fff3bba8964ed8b"
UEFIREPLACE_RELEASE_URL = "https://github.com/LongSoft/UEFITool/releases/tag/0.28.0"
UEFIREPLACE_DOWNLOAD_URL = "https://github.com/LongSoft/UEFITool/releases/download/0.28.0/UEFIReplace_0.28.0_win32.zip"
