import SwiftUI

enum HelpTopic: CaseIterable {
    case scan, sane, grouping, tiers, analysisNotes, focus, review, genres, delete, window

    var title: String {
        switch self {
        case .scan: "Choose photos, start or stop a scan"
        case .sane: "Set up SANE and choose scan settings"
        case .grouping: "How similar photos are grouped"
        case .tiers: "Understand keep, edit, and cull suggestions"
        case .analysisNotes: "What the analysis notes mean"
        case .focus: "Understand focus and subject boxes"
        case .review: "Use the photo card controls"
        case .genres: "Add, remove, and save genres"
        case .delete: "Delete or recover a photo"
        case .window: "Show the main window and find help"
        }
    }

    var paragraphs: [String] {
        switch self {
        case .scan:
            [
                "Use **Choose Files…** for images on disk or **Choose from Photos…** for your Photos library. Select up to 500 JPEG, HEIC, HEIF, PNG, or single-image TIFF images. The file picker also accepts PSD and compatible RAW files. Scanning starts when you confirm the selection.",
                "Choose **Scan Photos…** to open the scan panel. Choose a macOS scanner from **Scan with Image Capture**. If no scanner appears, use **Refresh Scanners** or **Open Image Capture…** to check whether macOS sees it. In the local build, **Framewise → Settings** can switch capture to installed SANE and choose the resolution, format, and color mode. The defaults are 600 dpi, TIFF, and 48-bit color. Use **Add Saved Sheet…** to review a sheet you captured separately. Framewise saves the master and extracted prints to Downloads by default. Use **Change…** before adding a sheet to choose another folder.",
                "Choose **Single photo**, **Separate prints**, or **Polaroids**. Leave space around each print on a contrasting backing. Framewise orients Polaroids with the wide border down, applies color correction by default, and retains the uncorrected crop. Turn off **Apply color correction to Polaroids** in Settings to keep the extracted colors. Splitting and rotation still apply. Add more sheets before clicking **Review Photos** to compare the whole batch.",
                "Framewise analyzes photos on your Mac. If Photos needs to download a selected image from iCloud, loading may take longer. The picker supplies an image version for Framewise to analyze and preview.",
                "Framewise reads the image’s embedded orientation and can turn sideways or upside-down previews when it finds strong evidence. The original orientation changes only when you choose **Save Rotation**.",
                "Thumbnails appear as photos become available during a scan. Related sets and review notes appear when analysis finishes. The progress bar tracks the current step. During **Compare photo pairs**, it counts comparisons between pairs of photos. After a scan, click **Processing time** in the toolbar for a breakdown of the analysis.",
                "Click **Stop Scan** to cancel loading or analysis. An operation already in progress may take a moment to stop. Use **Scan Again** to rerun the retained selection or choose a new batch. Scanning again clears unsaved rotations."
            ]
        case .sane:
            [
                "**Install SANE.** In Terminal, run `brew install sane-backends` if you use Homebrew. Framewise looks for the external `scanimage` executable in `/opt/homebrew/bin` or `/usr/local/bin`.",
                "**Check the scanner.** Connect and unlock the flatbed, then run `scanimage -L` in Terminal. If the scanner is missing, check the USB connection and close other scanning apps. Framewise prefers a single detected Canon LiDE 400 or uses the only scanner SANE finds.",
                "**Enable SANE (external dependency).** In **Framewise → Settings**, turn this on in the local build. It replaces **Scan with Image Capture** with **Scan with SANE** and reveals the SANE settings. The sandboxed Store candidate can open externally captured sheets through **Add Saved Sheet…**.",
                "**Resolution.** Choose 300, 600, or 1200 dpi. The default is 600 dpi. Higher resolutions take longer and produce larger files. Your scanner must support the chosen resolution.",
                "**Format.** Choose TIFF (default), PNG, or JPEG for the scan master. TIFF and PNG are lossless. JPEG is lossy and supports 24-bit color or 8-bit grayscale. Choose TIFF or PNG for modes that use 16-bit samples. Extracted review photos are saved as TIFFs.",
                "**Mode.** Choose 24-bit color (8 bits per RGB channel), 48-bit color (16 bits per RGB channel, the default), 8-bit grayscale, or 16-bit grayscale. Framewise checks the format and bit depth returned by SANE. Some scanners support only a subset of these modes.",
                "**Apply color correction to Polaroids.** This is on by default and applies to Polaroid sheets from either scanner source or **Add Saved Sheet…**. Turn it off to retain the scanned colors. Splitting and rotation still run, and the sheet master is preserved."
            ]
        case .grouping:
            [
                "Framewise compares each pair of photos using Apple Vision’s overall visual similarity and a second check for matching details within the images. This helps find alternate shots of a scene and can also find related crops or reframings.",
                "Matches form **Related sets** in the sidebar. A set can link through an intermediate photo, so two photos can be in the same set even if each only matches a third. **Ungrouped** contains the photos with no match in the selected batch.",
                "Use related sets to compare alternatives. The tier shown on each card is a separate suggestion based on quality and other signals."
            ]
        case .tiers:
            [
                "**Top Pick** is a strong candidate to keep. Within a related set, a photo can stand out for better face capture or subject detail. An ungrouped photo can stand out for its overall aesthetic score across the batch.",
                "**Keep & Review** is a candidate to keep, inspect more closely, or edit. Use the notes and full-resolution preview to decide what needs attention. You can make edits in your photo editor.",
                "**Possible Cull** means Framewise found a reason to consider removing the photo. Examples include low subject detail, lost detail in very bright or dark areas, closed eyes when an open-eye alternative exists, or possible reference material. Framewise assigns Possible Cull whenever it identifies possible reference material. Composition notes are advisory and cannot trigger Possible Cull on their own.",
                "Framewise compares related photos with their set and uses the full batch as a reference for ungrouped photos. Cards appear in tier order, then in the suggested order within each tier. There is no required number of picks or culls. A photo moves to Trash or Recently Deleted only after you choose **Delete…** and confirm."
            ]
        case .analysisNotes:
            [
                "**Rank within set** shows the card’s position in the displayed order and the number of photos in that set. For an ungrouped photo, the numbers refer to the Ungrouped list.",
                "**Possible reference material** means the image looks like something saved for information, such as a document or screenshot. Framewise puts it in **Possible Cull** so you can decide whether you still need it.",
                "**Less subject detail than full set** means this ungrouped photo scored near the bottom for subject detail across the batch.",
                "**A similar photo shows more subject detail** means a comparable shot in the same set shows substantially stronger fine detail on the same kind of subject.",
                "**Detail lost in bright or dark areas** means more pixels hit pure white or black than in the best comparison photo. Those areas can lose visible texture.",
                "**Eyes may be closed** means Framewise detected closed eyes on all faces it could assess and found an alternative with open eyes.",
                "**Possible poor composition** means the area that draws attention sits farther from the center or rule-of-thirds positions than in a comparison photo. This is a subjective suggestion and cannot trigger Possible Cull on its own.",
                "**Among the highest-rated photos in this review** means an ungrouped photo scored in the top tenth for overall appearance and had no flags that would put it in Possible Cull.",
                "**Best face capture in this set** means the photo’s strongest face-capture score stood out among the faces Framewise could assess in the set.",
                "**More subject detail than comparable shots** means finer detail measured consistently better than in the other photos of the same subject type in the set."
            ]
        case .focus:
            [
                "**Possible Missed Focus** appears when Framewise finds signs of softness. Click it to expand the details. Focus is assessed separately from the review tier.",
                "**A detected subject may be softer than its surroundings** means a detected face, person, or other subject has less measured detail than the area around it.",
                "**An area that draws attention may be soft** means Framewise checked a visually prominent region whose subject it couldn’t identify.",
                "**The whole photo shows less detail than other photos in this review** means both the overall image and its strongest detail areas scored low compared with the review batch.",
                "**Broad edge transitions suggest overall softness** means edges change gradually across the image, which can indicate soft focus.",
                "**Objectness region suggests softness** means an area that looks like an object showed low detail, but Framewise couldn’t identify what it was.",
                "**Relative focus: sharper** or **softer** compares fine detail with a directly matched photo that has a comparable subject. Framing and texture can affect the comparison.",
                "**Subject boxes** are on by default. Use the switch to hide them. Red marks faces, green people, orange animals, purple objects, and cyan attention areas."
            ]
        case .review:
            [
                "Choose a related set or **Ungrouped** in the sidebar. Each card shows its **Rank within set**, suggested tier, and any reasons or rotation notes. The sidebar totals count each tier across the review.",
                "Click **Zoom…** for a full-resolution preview. Use **Fit**, **100%**, **200%**, or **400%**, and scroll to inspect details. Click **Done** or press Escape to return to the review.",
                "Click the heart on a photo card or zoom preview to add or remove a Favorite. A filled heart means the photo is a Favorite. Framewise keeps the previous state until the change is saved.",
                "JPEG, PNG, TIFF and PSD Favorites are saved in the file when the edit can be made safely. HEIC, HEIF, RAW and other unsupported images keep Favorites for this review only. Hover over the heart to see when a Favorite lasts only for this review. Photos library Favorites use Photos’ own heart and require library access.",
                "Click **Rotate Left** to turn a card and its zoom preview by 90°. **Rotated … · Unsaved** means the preview has turned and the original still has its prior orientation. **Rotation saved** confirms that the change was applied. Click **Save Rotation** to apply it to the selected file or Photos asset. Files use a lossless orientation update when available. Photos keeps the original so you can revert the edit in Photos.",
                "For photos chosen from disk, click **Show in Finder** to reveal the original file. **Save to Photos** copies that file to your library after you grant permission to add photos. To import a RAW on its own, use **Save to Photos** on the RAW card."
            ]
        case .genres:
            [
                "Framewise suggests genres on your Mac for files and Photos selections. A photo can have multiple labels. If the evidence is inconclusive, the genre area stays blank. Use **Add Genre** or the remove button beside a label on the card or in **Zoom…**.",
                "**Portrait** covers people and expressions. **Landscape & Nature** covers outdoor scenery and cityscapes. **Street** covers candid public life. **Wildlife** covers animals in their habitats. **Sports & Action** covers athletic and fast-moving subjects. **Macro** covers extreme close-ups. **Architecture & Real Estate** covers buildings and interiors.",
                "Framewise saves genres automatically where supported. Disk files use embedded IPTC Keywords. Photos selections use native keywords on the selected library asset and require Photos access. A picker preview can supply the image for analysis while the keyword is saved to the library asset.",
                "**Genres are available for this review only.** means Framewise couldn’t save a keyword change. Hover over the message for the reason. RAW, HEIC, unsafe file layouts, and unavailable Photos access can lead to this message.",
                "**Automatic genre analysis unavailable.** means the classifier couldn’t return a result. You can still add a label manually.",
                "Removing a saved genre removes that keyword from the selected file or Photos library item. If Framewise can’t verify removal, it keeps the label visible.",
                "**Save to Photos** imports a disk original. With Photos read/write access, Framewise checks and adds embedded genre keywords that are missing on the imported asset. If the photo imports but its keywords can’t be verified, Framewise reports that separately."
            ]
        case .delete:
            [
                "For a disk file, click **Delete…** and confirm in Framewise. The file goes to the Mac Trash. To restore it, open Trash in Finder and choose **Put Back**.",
                ReviewRemoval.photosLibraryAccessEnabled
                    ? "For a Photos library item, click **Delete…** and confirm in the Photos system prompt. The item goes to **Recently Deleted** in Photos. macOS may ask for Photos access. To restore the photo, open **Recently Deleted** in Photos and choose **Recover**."
                    : "To delete a photo from your Photos library, use the Photos app. You can restore it from **Recently Deleted** in Photos.",
                "After deletion, use **Scan Again** to recalculate suggestions for the remaining photos. To review a recovered photo, select it again from Finder or Photos."
            ]
        case .window:
            [
                "Use the toolbar’s **Show Sidebar** or **Hide Sidebar** control to show or hide the list of related sets and tier totals.",
                "If the main window is minimized, hidden, or closed, choose **Window → Show Framewise** to bring it back. Scan results are available for the current session.",
                "Choose **Help → Framewise Help** and use the search field to search the topics. You can also open a topic directly from the Help menu. Choose **Framewise → About Framewise** to check the version."
            ]
        }
    }
}

struct FramewiseHelp: View {
    @Binding var topic: HelpTopic?
    @Binding var query: String

    private var matches: [HelpTopic] {
        let term = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !term.isEmpty else { return HelpTopic.allCases }
        return HelpTopic.allCases.filter {
            ([$0.title] + $0.paragraphs).joined(separator: " ").localizedStandardContains(term)
        }
    }

    var body: some View {
        NavigationSplitView {
            List(matches, id: \.self, selection: $topic) { topic in
                Text(topic.title)
            }
            .navigationSplitViewColumnWidth(min: 190, ideal: 235)
        } detail: {
            if let topic, matches.contains(topic) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        Text(topic.title).font(.title.bold()).accessibilityAddTraits(.isHeader)
                        ForEach(topic.paragraphs, id: \.self) { paragraph in
                            Text(LocalizedStringKey(paragraph))
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(24)
                }
            } else {
                ContentUnavailableView(matches.isEmpty ? "No matching topics" : "Choose a help topic",
                                       systemImage: "questionmark.circle")
            }
        }
        .searchable(text: $query, prompt: "Search Framewise Help")
        .onChange(of: query) {
            if !matches.contains(where: { $0 == topic }) { topic = matches.first }
        }
        .frame(minWidth: 580, minHeight: 340)
    }
}
