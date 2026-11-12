import SwiftUI

enum HelpTopic: CaseIterable {
    case scan, grouping, tiers, review, delete, window

    var title: String {
        switch self {
        case .scan: "Choose photos, start or stop a scan"
        case .grouping: "How similar photos are grouped"
        case .tiers: "Understand keep, edit, and cull suggestions"
        case .review: "Compare photos and zoom in"
        case .delete: "Delete or recover a photo"
        case .window: "Show the main window and find help"
        }
    }

    var paragraphs: [String] {
        switch self {
        case .scan:
            [
                "Use **Choose Files…** for images on disk or **Choose from Photos…** for your Photos library. Select up to 500 JPEG, HEIC, HEIF, PNG, or single-image TIFF images. The file picker also accepts PSD and compatible RAW files. Scanning starts when you confirm the selection.",
                "Framewise analyzes photos on your Mac. If Photos needs to download a selected image from iCloud, loading may take longer. The picker supplies an image version for Framewise to analyze and preview.",
                "Framewise automatically turns sideways or upside-down images for analysis and preview when it finds strong evidence of the correct orientation.",
                "The progress bar tracks the current step. During **Compare photo pairs**, it counts comparisons between pairs of photos. After a scan, click **Processing time** in the sidebar for a breakdown of the analysis.",
                "Click **Stop Scan** to cancel loading or analysis. An operation already in progress may take a moment to stop. Use **Scan Again** to rerun the retained selection or choose a new batch. Scanning again clears unsaved rotations."
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
                "**Possible Cull** means Framewise found a reason to consider removing the photo. Examples include low subject detail, lost detail in very bright or dark areas, closed eyes when an open-eye alternative exists, or an image identified as a utility image. Composition notes are advisory and cannot trigger Possible Cull on their own.",
                "Framewise compares related photos with their set and uses the full batch as a reference for ungrouped photos. Cards appear in tier order, then in the suggested order within each tier. There is no required number of picks or culls. A photo moves to Trash or Recently Deleted only after you choose **Delete…** and confirm."
            ]
        case .review:
            [
                "Choose a related set or **Ungrouped** in the sidebar. Each card shows its **Rank within set**, suggested tier, and any reasons or rotation notes. The sidebar totals count each tier across the review.",
                "**Possible Missed Focus** flags areas worth inspecting and is separate from the tier. **Relative focus** compares sharpness with a directly matched photo when the subjects are comparable.",
                "Turn on **Subject boxes** to see detected areas. Red marks faces, green people, orange animals, purple objects, and cyan attention areas.",
                "Click **Zoom…** for a full-resolution preview. Use **Fit**, **100%**, **200%**, or **400%**, and scroll to inspect details. Click **Done** or press Escape to return to the review.",
                "Click the heart on a photo card or zoom preview to add or remove a Favorite. A filled heart means the photo is a Favorite. Framewise keeps the previous state until the change is saved.",
                "JPEG, PNG, TIFF and PSD Favorites are saved in the file when the edit can be made safely. HEIC, HEIF, RAW and other unsupported images keep Favorites for this review only. A clock badge on the heart marks a Favorite that lasts only for this review. Photos library Favorites use Photos’ own heart and require library access.",
                "Click **Rotate Left** to turn a card and its zoom preview by 90°. The card marks an unsaved rotation. Click **Save Rotation** to apply it to the selected file or Photos asset. Files use a lossless orientation update when available. Photos keeps the original so you can revert the edit in Photos.",
                "For photos chosen from disk, click **Show in Finder** to reveal the original file. **Save to Photos** copies that file to your library after you grant permission to add photos. To import a RAW on its own, use **Save to Photos** on the RAW card."
            ]
        case .delete:
            [
                "Click **Delete…** on a photo card and confirm. A file on disk goes to the Mac Trash. To restore it, open Trash in Finder and choose **Put Back**.",
                ReviewRemoval.photosLibraryAccessEnabled
                    ? "When you delete a photo from your Photos library, Framewise moves it to **Recently Deleted** in Photos. macOS may ask for Photos access. To restore the photo, open **Recently Deleted** in Photos and choose **Recover**."
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
