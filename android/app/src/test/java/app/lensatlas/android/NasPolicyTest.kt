package app.lensatlas.android

import org.junit.Assert.*
import org.junit.Test

class NasPolicyTest {
    @Test fun authenticationQueriesAndScanCommandsMayPost() {
        listOf("/api/auth/login", "/api/stats", "/api/stats/focals", "/api/assets/query").forEach { assertTrue(NasPolicy.allowed("POST", it)) }
        listOf("/api/roots", "/api/jobs/1/cancel", "/api/backup", "/api/usage-notice/accept", "/api/auth/setup", "/api/player/open", "/api/connections").forEach { assertFalse(NasPolicy.allowed("POST", it)) }
        assertTrue(NasPolicy.allowed("POST","/api/roots/1/scan"))
        assertTrue(NasPolicy.allowed("POST","/api/jobs/12345678-1234-1234-1234-123456789abc/resume"))
        assertTrue(NasPolicy.allowed("GET","/api/jobs"))
        assertFalse(NasPolicy.allowed("POST","/api/roots/0/scan"))
        assertFalse(NasPolicy.validTarget("POST","/api/roots/1/scan?force=true"))
    }
    @Test fun allMutationMethodsAreDenied() {
        listOf("PUT", "PATCH", "DELETE").forEach { method ->
            listOf("/api/assets/1", "/api/roots/1", "/api/cache", "/api/connections/1").forEach { assertFalse(NasPolicy.allowed(method, it)) }
        }
    }
    @Test fun assetUrlsCannotEscapeAllowlist() {
        assertTrue(NasPolicy.allowed("GET", "/api/assets/12/thumbnail"))
        listOf("/api/assets/12/../cache", "/api/assets/12/stream", "/api/assets/12?url=evil", "/api/remote/1/api/cache").forEach { assertFalse(NasPolicy.allowed("GET", it)) }
    }
    @Test fun credentialsAndNonHttpAddressesAreRejected() {
        listOf("file:///photos", "https://user:pass@nas.test", "https://nas.test?q=1", "https://nas.test/#fragment").forEach { value ->
            assertThrows(IllegalArgumentException::class.java) { NasPolicy.base(value) }
        }
        assertEquals("https://nas.test/lens", NasPolicy.base(" https://nas.test/lens/ "))
    }
    @Test fun signedPreviewTargetsStayOnOriginalServer() {
        val sig = "a".repeat(64)
        assertTrue(NasPolicy.validTarget("GET", "/api/assets/1/thumbnail?expires=123&sig=$sig"))
        listOf("https://evil.test/api/assets/1/thumbnail", "//evil.test/api/assets/1/thumbnail", "/api/assets/1/thumbnail?url=evil", "/api/assets/%31/thumbnail?expires=123&sig=$sig").forEach { assertFalse(NasPolicy.validTarget("GET", it)) }
        assertFalse(NasPolicy.validTarget("POST", "/api/stats?redirect=evil"))
    }
}
