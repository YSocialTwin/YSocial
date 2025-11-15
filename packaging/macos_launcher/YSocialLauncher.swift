//
// YSocial Launcher for macOS
//
// This launcher displays a splash screen while launching the main YSocial application.
// It acts as a temporary window that shows the YSocial logo during app initialization.
//
// Build with: swiftc -parse-as-library -o YSocialLauncher YSocialLauncher.swift
//

import Cocoa
import Foundation

class SplashWindowController: NSWindowController {
    override func windowDidLoad() {
        super.windowDidLoad()
        
        // Configure window to be centered and always on top
        if let window = window {
            window.center()
            window.level = .floating
            window.makeKeyAndOrderFront(nil)
        }
    }
}

@NSApplicationMain
class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var imageView: NSImageView!
    var progressIndicator: NSProgressIndicator!
    var statusLabel: NSTextField!
    var ysocialProcess: Process?
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Create splash window
        let windowRect = NSRect(x: 0, y: 0, width: 500, height: 300)
        window = NSWindow(
            contentRect: windowRect,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        
        window.backgroundColor = NSColor(red: 0.1, green: 0.1, blue: 0.18, alpha: 1.0)
        window.isOpaque = true
        window.level = .floating
        window.center()
        
        // Create content view
        let contentView = NSView(frame: windowRect)
        window.contentView = contentView
        
        // Add logo image
        let logoRect = NSRect(x: 150, y: 150, width: 200, height: 100)
        imageView = NSImageView(frame: logoRect)
        imageView.imageScaling = .scaleProportionallyUpOrDown
        
        // Try to load YSocial logo
        if let logoPath = Bundle.main.path(forResource: "YSocial", ofType: "png"),
           let logoImage = NSImage(contentsOfFile: logoPath) {
            imageView.image = logoImage
        } else {
            // Fallback: Create text label if image not found
            let titleLabel = NSTextField(frame: logoRect)
            titleLabel.stringValue = "YSocial"
            titleLabel.font = NSFont.boldSystemFont(ofSize: 32)
            titleLabel.textColor = NSColor(red: 0.05, green: 0.58, blue: 0.91, alpha: 1.0)
            titleLabel.backgroundColor = .clear
            titleLabel.isBordered = false
            titleLabel.isEditable = false
            titleLabel.alignment = .center
            contentView.addSubview(titleLabel)
        }
        contentView.addSubview(imageView)
        
        // Add status label
        let statusRect = NSRect(x: 50, y: 80, width: 400, height: 30)
        statusLabel = NSTextField(frame: statusRect)
        statusLabel.stringValue = "Loading YSocial..."
        statusLabel.font = NSFont.systemFont(ofSize: 14)
        statusLabel.textColor = .white
        statusLabel.backgroundColor = .clear
        statusLabel.isBordered = false
        statusLabel.isEditable = false
        statusLabel.alignment = .center
        contentView.addSubview(statusLabel)
        
        // Add progress indicator
        let progressRect = NSRect(x: 200, y: 50, width: 100, height: 20)
        progressIndicator = NSProgressIndicator(frame: progressRect)
        progressIndicator.style = .spinning
        progressIndicator.startAnimation(nil)
        contentView.addSubview(progressIndicator)
        
        // Show window
        window.makeKeyAndOrderFront(nil)
        
        // Launch YSocial app after a brief delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.launchYSocialApp()
        }
    }
    
    func launchYSocialApp() {
        // Get the path to the actual YSocial executable
        // The launcher is in YSocial.app/Contents/MacOS/YSocialLauncher
        // The real app is in YSocial.app/Contents/MacOS/YSocial
        let launcherPath = Bundle.main.executablePath ?? ""
        let launcherDir = (launcherPath as NSString).deletingLastPathComponent
        let ysocialPath = (launcherDir as NSString).appendingPathComponent("YSocial")
        
        // Debug: Print paths
        print("Launcher path: \(launcherPath)")
        print("Launcher dir: \(launcherDir)")
        print("YSocial path: \(ysocialPath)")
        
        // Check if YSocial executable exists
        let fileManager = FileManager.default
        if !fileManager.fileExists(atPath: ysocialPath) {
            print("ERROR: YSocial executable not found at: \(ysocialPath)")
            showErrorAlert(message: "YSocial executable not found.\nExpected at: \(ysocialPath)")
            closeSplashAndQuit()
            return
        }
        
        // Launch the YSocial process
        ysocialProcess = Process()
        ysocialProcess?.executableURL = URL(fileURLWithPath: ysocialPath)
        ysocialProcess?.arguments = CommandLine.arguments.dropFirst().map { $0 }
        
        // Set the working directory to the MacOS directory
        // This ensures the PyInstaller app can find its resources
        ysocialProcess?.currentDirectoryURL = URL(fileURLWithPath: launcherDir)
        
        // Inherit environment variables from the launcher
        // This is important for PyInstaller to work correctly
        var environment = ProcessInfo.processInfo.environment
        // Ensure HOME is set (sometimes missing in app bundles)
        if environment["HOME"] == nil {
            environment["HOME"] = NSHomeDirectory()
        }
        ysocialProcess?.environment = environment
        
        // Set up standard output and error to capture any issues
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        ysocialProcess?.standardOutput = outputPipe
        ysocialProcess?.standardError = errorPipe
        
        // Monitor for when YSocial process ends
        ysocialProcess?.terminationHandler = { [weak self] process in
            print("YSocial process terminated with status: \(process.terminationStatus)")
            DispatchQueue.main.async {
                self?.closeSplashAndQuit()
            }
        }
        
        do {
            print("Launching YSocial...")
            try ysocialProcess?.run()
            print("YSocial process started successfully (PID: \(ysocialProcess?.processIdentifier ?? 0))")
            
            // Monitor for YSocial startup
            // Close splash after a reasonable startup time
            DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
                print("Closing splash after 5 seconds")
                self.closeSplashAndQuit()
            }
        } catch {
            print("Error launching YSocial: \(error)")
            showErrorAlert(message: "Failed to launch YSocial application.\n\nError: \(error.localizedDescription)")
            closeSplashAndQuit()
        }
    }
    
    func closeSplashAndQuit() {
        // Close splash window
        window?.close()
        
        // Quit launcher (but keep YSocial running)
        // Note: We don't terminate ysocialProcess, it continues running
        NSApplication.shared.terminate(nil)
    }
    
    func showErrorAlert(message: String) {
        let alert = NSAlert()
        alert.messageText = "YSocial Launch Error"
        alert.informativeText = message
        alert.alertStyle = .critical
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
    
    func applicationWillTerminate(_ notification: Notification) {
        // Ensure we don't kill the YSocial process when launcher quits
        ysocialProcess?.terminationHandler = nil
    }
}
