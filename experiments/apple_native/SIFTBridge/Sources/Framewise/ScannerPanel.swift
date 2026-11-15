import AppKit
import ImageCaptureCore
import ImageIO
import SwiftUI
import UniformTypeIdentifiers

enum ScannerPreference {
    static let externalSANE = "scanner.externalSANE"
    static let correctPolaroids = "scanner.correctPolaroids"
    static let saneResolution = "scanner.saneResolution"
    static let saneFormat = "scanner.saneFormat"
    static let saneMode = "scanner.saneMode"
}

private enum SANEFormat: String, CaseIterable, Sendable {
    case tiff, png, jpeg
    var type: UTType {
        switch self {
        case .tiff: .tiff
        case .png: .png
        case .jpeg: .jpeg
        }
    }
}

private enum SANEMode: String, CaseIterable, Sendable {
    case color24 = "Color"
    case color48 = "48 bits color"
    case gray8 = "Gray"
    case gray16 = "16 bits gray"

    var title: String {
        switch self {
        case .color24: "24-bit color"
        case .color48: "48-bit color"
        case .gray8: "8-bit grayscale"
        case .gray16: "16-bit grayscale"
        }
    }

    var depth: Int { self == .color48 || self == .gray16 ? 16 : 8 }
    var colorModel: String { self == .gray8 || self == .gray16 ? "Gray" : "RGB" }
}

private struct SANEOptions: Sendable {
    static let resolutions = [300, 600, 1200]
    static let defaultResolution = 600
    static let defaultFormat = SANEFormat.tiff
    static let defaultMode = SANEMode.color48
    static let jpegDepthMessage = "JPEG requires 24-bit color or 8-bit grayscale. Choose TIFF or PNG for 16-bit samples."

    let resolution: Int
    let format: SANEFormat
    let mode: SANEMode

    init(defaults: UserDefaults = .standard) {
        let dpi = defaults.integer(forKey: ScannerPreference.saneResolution)
        resolution = Self.resolutions.contains(dpi) ? dpi : Self.defaultResolution
        format = defaults.string(forKey: ScannerPreference.saneFormat).flatMap(SANEFormat.init(rawValue:)) ?? Self.defaultFormat
        mode = defaults.string(forKey: ScannerPreference.saneMode).flatMap(SANEMode.init(rawValue:)) ?? Self.defaultMode
    }
}

struct ScannerSettings: View {
    @AppStorage(ScannerPreference.externalSANE) private var externalSANE = false
    @AppStorage(ScannerPreference.correctPolaroids) private var correctPolaroids = true
    @AppStorage(ScannerPreference.saneResolution) private var resolution = SANEOptions.defaultResolution
    @AppStorage(ScannerPreference.saneFormat) private var format = SANEOptions.defaultFormat
    @AppStorage(ScannerPreference.saneMode) private var mode = SANEOptions.defaultMode

    var body: some View {
        Form {
            Toggle("Enable SANE (external dependency)", isOn: $externalSANE)
                .disabled(!ScannerBatch.saneAllowed)
            Text(ScannerBatch.saneAllowed
                 ? "Uses an installed scanimage tool."
                 : "External SANE is available in the local build.")
                .font(.caption).foregroundStyle(.secondary)
            if ScannerBatch.saneAllowed && externalSANE {
                Picker("Resolution", selection: $resolution) {
                    ForEach(SANEOptions.resolutions, id: \.self) { Text("\($0) dpi").tag($0) }
                }
                Picker("Format", selection: $format) {
                    ForEach(SANEFormat.allCases, id: \.self) { Text($0.rawValue.uppercased()).tag($0) }
                }
                Picker("Mode", selection: $mode) {
                    ForEach(SANEMode.allCases, id: \.self) { Text($0.title).tag($0) }
                }
                if format == .jpeg && mode.depth == 16 {
                    Text(SANEOptions.jpegDepthMessage).font(.caption).foregroundStyle(.secondary)
                }
            }
            Toggle("Apply color correction to Polaroids", isOn: $correctPolaroids)
            Text("Splitting and orientation apply in either case.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(20)
        .frame(width: 460)
    }
}

final class ScannerBatch: NSObject, ObservableObject, ICDeviceBrowserDelegate, ICScannerDeviceDelegate {
    @Published private(set) var scanners: [ICScannerDevice] = []
    private var browser: ICDeviceBrowser?
    private var discoveryTask: Task<Void, Never>?
    private static let lookingForScanners = "Looking for Image Capture scanners…"
    private static let noNativeScanner = "Image Capture found no scanner."

    func changeSource(usesSANE: Bool) {
        showStatus("Scan a sheet or add a saved sheet.")
        browse(!usesSANE)
    }
    private var scanner: ICScannerDevice?
    private var scanFolder: URL?
    private var scanFiles: [URL] = []
    private var waitingForFlatbed = false
    private var captureDate = Date()

    func browse(_ enabled: Bool) {
        if enabled && browser == nil {
            let browser = ICDeviceBrowser()
            browser.delegate = self
            browser.browsedDeviceTypeMask = ICDeviceTypeMask(rawValue: 0xFE00 | 0x0100 | 0x0002)!
            self.browser = browser
            showStatus(Self.lookingForScanners)
            discoveryTask = Task { @MainActor [weak self] in
                // Network scanners can arrive after local enumeration finishes.
                do { try await Task.sleep(for: .seconds(5)) } catch { return }
                guard let self, self.browser === browser, self.scanners.isEmpty,
                      !self.busy, self.status == Self.lookingForScanners else { return }
                self.showStatus(Self.noNativeScanner, isError: true)
            }
            browser.start()
        } else if !enabled {
            discoveryTask?.cancel()
            discoveryTask = nil
            let previous = browser
            browser = nil
            previous?.stop()
            scanners = []
        }
    }

    func refreshNativeScanners() {
        guard !busy else { return }
        browse(false)
        browse(true)
    }

    func openImageCapture() {
        if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.Image_Capture") {
            NSWorkspace.shared.openApplication(at: url, configuration: .init())
        } else {
            showStatus("Open Image Capture from Applications to check whether macOS sees your scanner.", isError: true)
        }
    }

    func captureNative(_ device: ICScannerDevice) {
        guard !busy else { return }
        if folder == nil { chooseFolder() }
        guard folder != nil else { return }
        let temporary = FileManager.default.temporaryDirectory
            .appendingPathComponent("FramewiseICA-\(UUID())", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: false,
                                                    attributes: [.posixPermissions: 0o700])
        } catch { showStatus(error.localizedDescription, isError: true); return }
        scanFolder = temporary
        scanFiles = []
        captureDate = Date()
        scanner = device
        busy = true
        showStatus("Connecting to scanner…")
        device.delegate = self
        device.requestOpenSession()
    }

    func deviceBrowser(_ browser: ICDeviceBrowser, didAdd device: ICDevice, moreComing: Bool) {
        guard self.browser === browser, let scanner = device as? ICScannerDevice,
              !scanners.contains(scanner) else { return }
        scanners.append(scanner)
        if !busy && (status == Self.lookingForScanners || status == Self.noNativeScanner) {
            showStatus("Choose an Image Capture scanner or add a saved sheet.")
        }
    }

    func deviceBrowser(_ browser: ICDeviceBrowser, didRemove device: ICDevice, moreGoing: Bool) {
        guard self.browser === browser else { return }
        let hadScanners = !scanners.isEmpty
        scanners.removeAll { $0 === device }
        didRemove(device)
        if hadScanners && scanners.isEmpty && !busy && !statusIsError {
            showStatus(Self.noNativeScanner, isError: true)
        }
    }

    func didRemove(_ device: ICDevice) {
        if scanner === device { finishNative("The scanner disconnected.") }
    }

    func device(_ device: ICDevice, didCloseSessionWithError error: Error?) {
        if scanner === device { finishNative(error?.localizedDescription ?? "The scanner session closed.") }
    }

    func device(_ device: ICDevice, didOpenSessionWithError error: Error?) {
        guard let scanner, scanner === device else { return }
        if let error { finishNative(error.localizedDescription); return }
        guard scanner.availableFunctionalUnitTypes.contains(NSNumber(value: ICScannerFunctionalUnitType.flatbed.rawValue))
        else { finishNative("This workflow needs a flatbed scanner."); return }
        waitingForFlatbed = true
        scanner.requestSelect(.flatbed)
    }

    func scannerDevice(_ device: ICScannerDevice, didSelect unit: ICScannerFunctionalUnit, error: Error?) {
        guard scanner === device, waitingForFlatbed, let scanFolder else { return }
        if let error { finishNative(error.localizedDescription); return }
        guard unit.type == .flatbed else { finishNative("Couldn’t select the scanner’s flatbed."); return }
        waitingForFlatbed = false
        if let resolution = [600, 300].first(where: unit.supportedResolutions.contains) { unit.resolution = resolution }
        unit.pixelDataType = .RGB
        if unit.supportedBitDepths.contains(Int(ICScannerBitDepth.depth16Bits.rawValue)) {
            unit.bitDepth = .depth16Bits
        } else if unit.supportedBitDepths.contains(Int(ICScannerBitDepth.depth8Bits.rawValue)) {
            unit.bitDepth = .depth8Bits
        }
        unit.scanArea = CGRect(origin: .zero, size: unit.physicalSize)
        device.transferMode = .fileBased
        device.documentName = "Sheet"
        device.documentUTI = UTType.tiff.identifier
        device.downloadsDirectory = scanFolder
        showStatus("Scanning with Image Capture…")
        device.requestScan()
    }

    func scannerDevice(_ device: ICScannerDevice, didScanTo url: URL) {
        if scanner === device { scanFiles.append(url) }
    }

    func scannerDevice(_ device: ICScannerDevice, didCompleteScanWithError error: Error?) {
        if scanner === device { finishNative(error?.localizedDescription) }
    }

    private func finishNative(_ error: String?) {
        let device = scanner
        let files = scanFiles
        let directory = scanFolder
        scanner = nil
        scanFiles = []
        scanFolder = nil
        waitingForFlatbed = false
        device?.requestCloseSession()
        let cleanup = { if let directory { Self.removeEmptyCaptureFolder(directory) } }
        if !files.isEmpty {
            prepare(files, layout: layout, date: captureDate, capturedIn: directory, cleanup: cleanup)
        } else {
            cleanup()
            showStatus(error ?? "The scanner didn’t return a sheet.", isError: true)
            busy = false
        }
    }

    @Published private(set) var sheets = 0
    @Published private(set) var photos: [URL] = []
    @Published private(set) var busy = false
    @Published private(set) var status = "Scan a sheet or add a saved sheet."
    @Published private(set) var statusIsError = false

    private func showStatus(_ message: String, isError: Bool = false) {
        status = message
        statusIsError = isError
    }
    @Published var layout: ScanLayout = .polaroids
    @Published private(set) var folder: URL? = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
    private var destinationScoped = false

    func stop() {
        browse(false)
        if destinationScoped { folder?.stopAccessingSecurityScopedResource() }
        destinationScoped = false
    }

    func chooseFolder() {
        guard !busy else { return }
        let panel = NSOpenPanel()
        panel.title = "Choose where to keep sheet masters and extracted photos"
        panel.directoryURL = folder
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.canCreateDirectories = true
        if panel.runModal() == .OK, let url = panel.url {
            if destinationScoped { folder?.stopAccessingSecurityScopedResource() }
            folder = url
            destinationScoped = url.startAccessingSecurityScopedResource()
        }
    }

    static let saneAllowed = Bundle.main.object(forInfoDictionaryKey: "FramewiseExternalSANE") as? Bool == true

    func captureSANE() {
        guard Self.saneAllowed, !busy else { return }
        if folder == nil { chooseFolder() }
        guard folder != nil else { return }
        guard let executable = ["/opt/homebrew/bin/scanimage", "/usr/local/bin/scanimage"]
            .first(where: FileManager.default.isExecutableFile(atPath:)) else {
            showStatus("SANE scanimage is missing. Install SANE or add a saved 48-bit TIFF.", isError: true)
            return
        }
        let options = SANEOptions()
        guard options.format != .jpeg || options.mode.depth == 8 else {
            showStatus(SANEOptions.jpegDepthMessage, isError: true)
            return
        }
        let layout = layout
        let date = Date()
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("FramewiseSANE-\(UUID())")
        busy = true
        showStatus("Scanning via SANE · \(options.resolution) dpi · \(options.mode.title) · \(options.format.rawValue.uppercased())…")
        Task { @MainActor in
            do {
                let file = try await Task.detached(priority: .userInitiated) {
                    try Self.runSANE(executable: executable, in: directory, options: options)
                }.value
                prepare([file], layout: layout, date: date, capturedIn: directory) {
                    Self.removeEmptyCaptureFolder(directory)
                }
            } catch {
                busy = false
                showStatus(error.localizedDescription, isError: true)
                Self.removeEmptyCaptureFolder(directory)
            }
        }
    }

    private static func removeEmptyCaptureFolder(_ folder: URL) {
        if (try? FileManager.default.contentsOfDirectory(atPath: folder.path).isEmpty) == true {
            try? FileManager.default.removeItem(at: folder)
        }
    }

    private static func runSANE(executable: String, in directory: URL, options: SANEOptions) throws -> URL {
        let manager = FileManager.default
        try manager.createDirectory(at: directory, withIntermediateDirectories: false,
                                    attributes: [.posixPermissions: 0o700])
        let inspection = directory.appendingPathComponent("devices.txt")
        func run(_ arguments: [String], stdout: FileHandle) throws {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = arguments
            process.standardOutput = stdout
            process.standardError = FileHandle.nullDevice
            try process.run()
            process.waitUntilExit()
            guard process.terminationStatus == 0 else {
                throw ScanCaptureError.sane("SANE exited with status \(process.terminationStatus). Check that the scanner is connected and not open in another app.")
            }
        }
        try Data().write(to: inspection, options: .withoutOverwriting)
        defer { try? manager.removeItem(at: inspection) }
        let log = try FileHandle(forWritingTo: inspection)
        defer { try? log.close() }
        try run(["--formatted-device-list=%d\t%m%n"], stdout: log)
        let devices = try String(contentsOf: inspection, encoding: .utf8).split(whereSeparator: \.isNewline)
        let lide = devices.filter { $0.split(separator: "\t", maxSplits: 1).last?.localizedCaseInsensitiveContains("LiDE 400") == true }
        let choices = lide.isEmpty ? devices : lide
        guard choices.count == 1, let device = choices.first?.split(separator: "\t", maxSplits: 1).first else {
            throw ScanCaptureError.sane(choices.isEmpty ? "SANE found no scanner." : "Connect only the SANE scanner you want to use.")
        }
        let file = directory.appendingPathComponent("Sheet").appendingPathExtension(options.format.rawValue)
        do {
            try run(["--device-name", String(device), "--source", "Flatbed", "--mode", options.mode.rawValue,
                     "--resolution", String(options.resolution), "--format=\(options.format.rawValue)", "--output-file", file.path], stdout: .nullDevice)
            try verifyCapture(file, options: options)
            return file
        } catch {
            if manager.fileExists(atPath: file.path) {
                throw ScanCaptureError.sane("\(error.localizedDescription) The scanner’s file is still at \(file.path).")
            }
            throw error
        }
    }

    private static func verifyCapture(_ file: URL, options: SANEOptions) throws {
        guard let source = CGImageSourceCreateWithURL(file as CFURL, nil),
              CGImageSourceGetType(source) as String? == options.format.type.identifier,
              CGImageSourceGetCount(source) == 1,
              CGImageSourceGetStatus(source) == .statusComplete,
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as NSDictionary?,
              properties[kCGImagePropertyDepth] as? Int == options.mode.depth,
              properties[kCGImagePropertyColorModel] as? String == options.mode.colorModel,
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil),
              image.bitsPerComponent == options.mode.depth,
              CGImageSourceGetStatusAtIndex(source, 0) == .statusComplete else {
            throw ScanCaptureError.sane("The scanner did not return a complete \(options.mode.title) \(options.format.rawValue.uppercased()) file.")
        }
    }

    func addSheet() {
        guard !busy else { return }
        if folder == nil { chooseFolder() }
        guard folder != nil else { return }
        let panel = NSOpenPanel()
        panel.title = "Choose a scanned sheet"
        panel.allowedContentTypes = [.tiff, .jpeg, .png]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let scoped = url.startAccessingSecurityScopedResource()
        prepare([url], layout: layout, date: Date(), capturedIn: nil) {
            if scoped { url.stopAccessingSecurityScopedResource() }
        }
    }

    private func prepare(_ files: [URL], layout: ScanLayout, date: Date, capturedIn: URL?, cleanup: @escaping () -> Void) {
        guard let folder else { cleanup(); busy = false; return }
        busy = true
        showStatus("Preparing scanned photos…")
        let correctPolaroids = UserDefaults.standard.object(forKey: ScannerPreference.correctPolaroids) as? Bool ?? true
        Task { @MainActor in
            defer { cleanup(); busy = false }
            for file in files {
                do {
                    let output = try await Task.detached(priority: .userInitiated) {
                        let formatter = DateFormatter()
                        formatter.locale = Locale(identifier: "en_US_POSIX")
                        formatter.dateFormat = "yyyy-MM-dd"
                        let name = "Framewise-\(formatter.string(from: date))-\(UUID().uuidString)"
                        let sheet = folder.appendingPathComponent(name, isDirectory: true)
                        try FileManager.default.createDirectory(at: sheet, withIntermediateDirectories: false)
                        let master = sheet.appendingPathComponent("Master").appendingPathExtension(file.pathExtension)
                        try FileManager.default.copyItem(at: file, to: master)
                        if file.deletingLastPathComponent().standardizedFileURL == capturedIn?.standardizedFileURL {
                            try? FileManager.default.removeItem(at: file)
                        }
                        do {
                            return try ScanSheet.process(master: master, layout: layout, in: sheet, correctPolaroids: correctPolaroids)
                        } catch {
                            throw ScanCaptureError.masterKept(sheet.lastPathComponent, error.localizedDescription)
                        }
                    }.value
                    guard photos.count + output.count <= 500 else {
                        showStatus("Photos were saved to disk. A single review can contain up to 500 photos.", isError: true)
                        return
                    }
                    photos += output
                    sheets += 1
                    showStatus("Ready to review. Add another sheet or start the review.")
                } catch {
                    showStatus("\(layout.rawValue): \(error.localizedDescription)", isError: true)
                    if let capturedIn, FileManager.default.fileExists(atPath: file.path) {
                        status += " The scanner’s file is still in \(capturedIn.path)."
                    }
                    return
                }
            }
        }
    }


}

private enum ScanCaptureError: LocalizedError {
    case sane(String)
    case masterKept(String, String)
    var errorDescription: String? {
        switch self {
        case let .sane(reason): reason
        case let .masterKept(folder, reason): "\(reason) The sheet master is in \(folder)."
        }
    }
}

struct ScannerPanel: View {
    @StateObject private var batch = ScannerBatch()
    @AppStorage(ScannerPreference.externalSANE) private var externalSANE = false
    private var usesSANE: Bool { ScannerBatch.saneAllowed && externalSANE }
    @Environment(\.dismiss) private var dismiss
    let review: ([URL], URL) -> Void
    private var canReview: Bool { !batch.busy && !batch.photos.isEmpty }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Scan Photos").font(.title.bold())
            Picker("Sheet layout", selection: $batch.layout) {
                ForEach(ScanLayout.allCases) { Text($0.rawValue).tag($0) }
            }.disabled(batch.busy)
            HStack {
                Text("Save to: \(batch.folder?.lastPathComponent ?? "Choose folder")")
                    .help(batch.folder?.path ?? "")
                Button("Change…") { batch.chooseFolder() }.disabled(batch.busy || !batch.photos.isEmpty)
            }
            Text("Separate prints on a contrasting backing. For Polaroids, place up to four prints with space around each border.")
                .foregroundStyle(.secondary)
            HStack {
                if usesSANE {
                    Button("Scan with SANE") { batch.captureSANE() }.disabled(batch.busy)
                } else {
                    Menu("Scan with Image Capture") {
                        ForEach(batch.scanners, id: \.self) { scanner in
                            Button(scanner.name ?? "Scanner") { batch.captureNative(scanner) }
                        }
                        if batch.scanners.isEmpty {
                            Text("No Image Capture scanners found")
                        }
                        Divider()
                        Button("Refresh Scanners") { batch.refreshNativeScanners() }
                        Button("Open Image Capture…") { batch.openImageCapture() }
                    }
                    .disabled(batch.busy)
                    .help("Choose a scanner or refresh discovery.")
                }
                Button("Add Saved Sheet…") { batch.addSheet() }.disabled(batch.busy)
                if batch.busy { ProgressView().controlSize(.small) }
            }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                if batch.statusIsError {
                    Image(systemName: "exclamationmark.circle.fill")
                        .accessibilityLabel("Error")
                }
                Text(batch.status).textSelection(.enabled)
            }
                .fontWeight(batch.statusIsError ? .bold : .regular)
                .foregroundStyle(batch.statusIsError ? Color.red : Color.primary)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
            Text("\(batch.sheets) sheets · \(batch.photos.count) photos").foregroundStyle(.secondary)
            HStack {
                Button("Close") { dismiss() }.disabled(batch.busy)
                Spacer()
                Button("Review Photos") {
                    if let folder = batch.folder {
                        review(batch.photos, folder)
                        dismiss()
                    }
                }.buttonStyle(.bordered).disabled(!canReview)
            }
        }
        .padding(24)
        .frame(width: 510)
        .interactiveDismissDisabled(batch.busy)
        .onAppear { batch.browse(!usesSANE) }
        .onChange(of: usesSANE) { _, enabled in batch.changeSource(usesSANE: enabled) }
        .onDisappear { batch.stop() }
    }
}
