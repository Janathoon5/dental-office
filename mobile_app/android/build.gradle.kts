import org.jetbrains.kotlin.gradle.tasks.KotlinCompile

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)

    // Some older plugins (e.g. flutter_jailbreak_detection 1.10.0) predate
    // AGP's namespace requirement and only declare a manifest `package`
    // attribute, which modern AGP no longer falls back to. Backfill the
    // namespace from that attribute for any subproject missing one, rather
    // than patching the plugin's pub-cache copy directly. Registered here,
    // before evaluationDependsOn below forces early evaluation of some
    // subprojects, since afterEvaluate can't be added once a project has
    // already been evaluated.
    afterEvaluate {
        extensions.findByName("android")?.let { ext ->
            val android = ext as com.android.build.gradle.BaseExtension
            if (android.namespace == null) {
                val manifestFile = android.sourceSets.getByName("main").manifest.srcFile
                val packageMatch = Regex("""package="([^"]+)"""").find(manifestFile.readText())
                android.namespace = packageMatch?.groupValues?.get(1)
            }
        }

        // Plugins in this project's dependency tree (screen_protector,
        // local_auth's transitive deps, etc.) each pin their own Java/Kotlin
        // JVM target inconsistently against whatever JDK Gradle itself runs
        // under, causing "Inconsistent JVM Target Compatibility" build
        // failures. Force both to Java 17 uniformly project-wide instead of
        // patching each plugin's build.gradle individually.
        tasks.withType<JavaCompile>().configureEach {
            sourceCompatibility = "17"
            targetCompatibility = "17"
        }
        tasks.withType<KotlinCompile>().configureEach {
            compilerOptions {
                jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
            }
        }
    }
}
subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
