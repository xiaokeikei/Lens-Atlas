package app.lensatlas.android

import android.app.Activity
import android.content.Intent
import android.view.View
import android.view.ViewGroup
import android.webkit.WebView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

@RunWith(AndroidJUnit4::class)
class WebViewBridgeTest {
    private val instrumentation=InstrumentationRegistry.getInstrumentation()
    private fun findWeb(view:View):WebView? {
        if(view is WebView)return view
        if(view is ViewGroup)for(i in 0 until view.childCount)findWeb(view.getChildAt(i))?.let { return it }
        return null
    }
    private fun evaluate(web:WebView,js:String):String {
        val result=AtomicReference<String>();val latch=CountDownLatch(1)
        instrumentation.runOnMainSync { web.evaluateJavascript(js){result.set(it);latch.countDown()} }
        check(latch.await(5,TimeUnit.SECONDS)){ "WebView response timed out" }
        return result.get()
    }
    private fun waitFor(web:WebView,expression:String):String {
        var value="null"
        repeat(80){value=evaluate(web,expression);if(value=="true")return value;Thread.sleep(100)}
        return value
    }
    @Test fun bundledReactRendersAndBridgeRejectsWriteActions() {
        org.junit.Assume.assumeNotNull(WebView.getCurrentWebViewPackage())
        val activity=instrumentation.startActivitySync(Intent(instrumentation.targetContext,MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        try {
            val web=findWeb(activity.findViewById(android.R.id.content))!!
            assertEquals("true",waitFor(web,"Boolean(document.querySelector('.mobile-nav'))"))
            assertEquals("4",evaluate(web,"document.querySelectorAll('.mobile-nav button').length"))
            assertEquals("true",evaluate(web,"document.querySelector('.brand').innerText.includes('镜迹')"))
            assertEquals("true",waitFor(web,"Boolean(document.querySelector('.mobile-context'))"))
            evaluate(web,"(function(){window.__testReply=null;const previous=window.__lensReply;window.__lensReply=(id,json)=>{if(id===900001)window.__testReply=JSON.parse(json);else previous(id,json);};LensAndroid.request(900001,'delete','{}');return true;})()")
            assertEquals("true",waitFor(web,"Boolean(window.__testReply && window.__testReply.error==='只读客户端禁止此操作')"))
            evaluate(web,"(function(){window.__externalBlocked=false;fetch('https://example.com').catch(()=>window.__externalBlocked=true);return true;})()")
            assertEquals("true",waitFor(web,"window.__externalBlocked"))
        } finally { instrumentation.runOnMainSync { activity.finish() } }
    }
}
