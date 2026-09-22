# Verification

The Python calculation and OOXML-preserving write path were executed on Linux with NumPy/SciPy against the three supplied workbooks. No student files are included in this package.

Checked: participant count reconciliation, same-level cap, 3/3a separation, group fragmentation, overflow-room quota, dedicated and special placement, successful fixed-room-count increase, infeasible reduction rejection, preservation of every archive part except participant cells and Excel recalculation metadata. VBA bytes remain identical.

Windows launcher and PyInstaller packaging require verification on Windows 10/11 x64. They have not been executed in Windows in this environment. No prebuilt Windows EXE is included.

Optimizer time limits are intentional. An undecided smaller room count stops the search rather than allowing a false minimum claim. Valid incumbents are labeled if balance/split optimality was not proved.

Version 5 verification: the complete local HTTP upload/calculate/download flow was executed against an XLSM workbook. The generated matrix reconciled all participant, teacher/unit, and room totals; its check column was zero for every row. The new RTL worksheet loaded successfully with frozen panes and formatting. The VBA project bytes remained identical. Reprocessing an output workbook replaced the existing matrix sheet instead of duplicating it.

Version 5.1 correction: worksheet child elements are emitted in SpreadsheetML schema order (`autoFilter` before `mergeCells`), and invalid XML control characters are removed from displayed labels. This corrects Microsoft Excel recovery of the generated matrix worksheet.

Version 6 verification: the local HTTP upload, assignment, XLSM download, envelope generation, PDF download and output-directory save flow were executed end to end. The test workbook produced 70 assigned participants in five rooms and a five-page A4 PDF. PDF headers, blank physical-room box, full-width six-hour invigilation roster, Hebrew RTL display, room note, accommodations, blank attendance/submission columns and unit summaries were visually inspected after rasterizing the output. Printed pages intentionally contain neither application credit nor page numbering. A separate synthetic two-room PDF is included; it contains no real student data.

The Inno Setup and PyInstaller configuration is included, but a native Windows installer cannot be compiled or executed in this Linux test environment. Run `Build_Installer.cmd` or the included GitHub Actions workflow on Windows, then verify installation, shortcuts, progress UI, launch and uninstall on clean Windows 10 and Windows 11 x64 systems before distribution.
