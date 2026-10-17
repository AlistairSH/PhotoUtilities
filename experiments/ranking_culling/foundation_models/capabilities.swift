import Foundation
import FoundationModels
let model = SystemLanguageModel.default
let row: [String: Any] = ["availability": String(describing: model.availability),
 "vision": model.capabilities.contains(.vision), "guided_generation": model.capabilities.contains(.guidedGeneration),
 "variant": model.variant.displayName, "context_size": model.contextSize,
 "os": ProcessInfo.processInfo.operatingSystemVersionString, "physical_memory": ProcessInfo.processInfo.physicalMemory]
FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: row, options: [.sortedKeys]))
